#!/usr/bin/env python

"""Parse Terraform state and create GitHub secrets.

Secrets are created for IAM access keys, and specially tagged resources.

For each IAM access key two secrets will be created:
 - AWS_ACCESS_KEY_ID
 - AWS_SECRET_ACCESS_KEY

If there is only one access key, the secrets will be named as above.  If more than one
key exists in the Terraform state, the key's associated user will be appended to the
secret's name.
 - AWS_ACCESS_KEY_ID_BUILDER
 - AWS_SECRET_ACCESS_KEY_BUILDER

Resources tagged with "GitHub_Secret_Name" and "GitHub_Secret_Terraform_Lookup" will
have a single secret created based on the tag contents.  For example if a resource had
these tags:
 - GitHub_Secret_Name: BUILD_ROLE_TO_ASSUME
 - GitHub_Secret_Terraform_Lookup: arn

A secret would be generated with the name "BUILD_ROLE_TO_ASSUME" and the value of
the resource's ARN.

This tool is most effective when executed in the directory containing the .terraform
state directory, within a GitHub project.  It will attempt to detect the repository
name from the project's git origin.  Options exist to provide the repository name or
Terraform state manually.

It requires a Personal Access Token from GitHub that has "repo" access scope.  Tokens
can be saved to the keychain service for future use by using the "save" command.

Usage:
  terraform-to-secrets [options]
  terraform-to-secrets save <github-personal-access-token>

  terraform-to-secrets (-h | --help)

Options:
  -d --dry-run           Don't create secrets.  Just log what would be created.
  -h --help              Show this message.
  -l --log-level=LEVEL   If specified, then the log level will be set to
                         the specified value.  Valid values are "debug", "info",
                         "warning", "error", and "critical". [default: info]
  -r --repo=REPONAME     Use provided repository name instead of detecting it.
  -s --state=JSONFILE    Read state from a file instead of asking Terraform.
  -t --token=PAT         Specify a GitHub personal access token (PAT).
"""

# Standard Python Libraries
from base64 import b64encode
import json
import logging
import re
import subprocess  # nosec : security implications have been considered
import sys
from typing import Any, Dict, Generator, Optional, Tuple, Union

# Third-Party Libraries
import docopt
import keyring
from nacl import encoding, public
import requests
from schema import And, Or, Schema, SchemaError, Use

# Constants
GIT_URL_RE: re.Pattern = re.compile("(?:git@|https://)github.com[:/](.*).git")
GITHUB_SECRET_NAME_TAG: str = "GitHub_Secret_Name"
GITHUB_SECRET_TERRAFORM_LOOKUP_TAG: str = "GitHub_Secret_Terraform_Lookup"
KEYRING_SERVICE = "terraform-to-secrets"
KEYRING_USERNAME = "GitHub PAT"


def get_terraform_state(filename: str = "") -> Dict:
    """Retrieve IAM credentials from Terraform state.

    Returns the Terraform state as a dict.
    """
    data: Union[str, bytes, bytearray]
    if filename:
        logging.info(f"Reading state from json file {filename}")
        with open(filename) as f:
            data = f.read()
    else:
        logging.info("Reading state from Terraform command.")
        process = subprocess.run(  # nosec
            ["terraform", "show", "--json"], stdout=subprocess.PIPE
        )
        data = process.stdout
    # Normally we'd check the process return code here.  But Terraform is perfectly
    # happy to return zero even if there were no state files.
    json_state: Dict = json.loads(data)

    if not json_state.get("values"):
        logging.critical("Is there a .terraform state directory here?")
        raise Exception("No Terraform state found.")
    return json_state


def find_tagged_secret(
    resource_name: str, resource_data: Dict
) -> Generator[Tuple[str, str], None, None]:
    """Extract a tagged secret from a resource."""
    # Ensure "tags" key exists in resource_data and if it does, make sure
    # its value is not None.  Both of these cases can occur.
    tags: Dict[str, str]
    if "tags" not in resource_data or resource_data.get("tags") is None:
        tags = dict()
    else:
        tags = resource_data["tags"]

    secret_name: Optional[str] = tags.get(GITHUB_SECRET_NAME_TAG)
    lookup_tag: Optional[str] = tags.get(GITHUB_SECRET_TERRAFORM_LOOKUP_TAG)
    secret_value: Optional[str]
    if secret_name:
        logging.debug(
            f"Found {GITHUB_SECRET_NAME_TAG} on {resource_name} "
            f"with value {secret_name}"
        )
        if lookup_tag:
            logging.debug(
                f"Found {GITHUB_SECRET_TERRAFORM_LOOKUP_TAG} on "
                f"{resource_name} with value {lookup_tag}"
            )
            secret_value = resource_data.get(lookup_tag)
            if secret_value is None:
                logging.warning(f"Could not lookup value with key {lookup_tag}")
            else:
                logging.debug(f"Looked up value: {secret_value}")
                yield secret_name, secret_value
        else:
            logging.warning(
                f"Missing {GITHUB_SECRET_TERRAFORM_LOOKUP_TAG} on " f"{resource_name}."
            )
    return


def find_outputs(terraform_state: Dict) -> Generator[Dict, None, None]:
    """Search for resources with outputs in the Terraform state."""
    for resource in terraform_state["values"]["root_module"].get("resources", []):
        if resource.get("values", dict()).get("outputs", dict()):
            yield resource["values"]["outputs"]


def parse_tagged_outputs(
    terraform_state: Dict,
) -> Generator[Tuple[str, str], None, None]:
    """Search all outputs for tags requesting the creation of a secret."""
    for outputs in find_outputs(terraform_state):
        for output_name, output_data in outputs.items():
            yield from find_tagged_secret(output_name, output_data)
    return


def find_resources_in_child_modules(
    child_modules: list, resource_type: Optional[str]
) -> Generator[Dict, None, None]:
    """
    Search for resources of a certain type in a Terraform child_modules list.

    resource_type None yields all resources.
    """
    for child_module in child_modules:
        for resource in child_module.get("resources", []):
            if resource_type is None or resource["type"] == resource_type:
                yield resource

        if "child_modules" in child_module:
            for resource in find_resources_in_child_modules(
                child_module["child_modules"], resource_type
            ):
                yield resource


def find_resources(
    terraform_state: Dict, resource_type: Optional[str]
) -> Generator[Dict, None, None]:
    """Search for resources of a certain type in the Terraform state.

    resource_type None yields all resources.
    """
    for resource in terraform_state["values"]["root_module"].get("resources", []):
        if resource_type is None or resource["type"] == resource_type:
            yield resource

    if "child_modules" in terraform_state["values"]["root_module"]:
        for resource in find_resources_in_child_modules(
            terraform_state["values"]["root_module"]["child_modules"], resource_type
        ):
            yield resource


def parse_creds(terraform_state: Dict) -> Generator[Tuple[str, str, str], None, None]:
    """Search for IAM access keys in resources.

    Yields (user, key_id, secret) when found.
    """
    for resource in find_resources(terraform_state, "aws_iam_access_key"):
        key_id: str = resource["values"]["id"]
        secret: str = resource["values"]["secret"]
        user: str = resource["values"]["user"]
        yield user, key_id, secret
    return


def parse_tagged_resources(
    terraform_state: Dict,
) -> Generator[Tuple[str, str], None, None]:
    """Search all resources for tags requesting the creation of a secret."""
    for resource in find_resources(terraform_state, None):
        yield from find_tagged_secret(resource["address"], resource["values"])
    return


def encrypt(public_key: str, secret_value: str) -> str:
    """Encrypt a Unicode string using the public key."""
    public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")


def get_public_key(session: requests.Session, repo_name) -> Dict[str, str]:
    """Fetch the public key for a repository."""
    logging.info(f"Requesting public key for repository {repo_name}")
    response = session.get(
        f"https://api.github.com/repos/{repo_name}/actions/secrets/public-key"
    )
    response.raise_for_status()
    return response.json()


def set_secret(
    session: requests.Session,
    repo_name: str,
    secret_name: str,
    secret_value: str,
    public_key: Dict[str, str],
) -> None:
    """Create a secret in a repository."""
    logging.info(f"Creating secret {secret_name}")
    encrypted_secret_value = encrypt(public_key["key"], secret_value)
    response = session.put(
        f"https://api.github.com/repos/{repo_name}/actions/secrets/{secret_name}",
        json={
            "encrypted_value": encrypted_secret_value,
            "key_id": public_key["key_id"],
        },
    )
    response.raise_for_status()


def get_repo_name() -> str:
    """Get the repository name using git."""
    logging.debug("Trying to determine GitHub repository name using git.")
    c = subprocess.run(  # nosec
        ["git", "remote", "get-url", "origin"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if c.returncode != 0:
        logging.critical("Could not determine GitHub repository name.")
        raise Exception(c.stderr)
    match = GIT_URL_RE.match(c.stdout.decode())
    if match:
        repo_name = match.groups()[0]  # type: ignore
    else:
        logging.critical("Could not determine GitHub repository name.")
        logging.critical("Use the --repo option to specify it manually.")
        raise Exception("Could not determine GitHub repository name.")
    return repo_name


def get_users(terraform_state: Dict) -> Dict[str, Tuple[str, str]]:
    """Return a dictionary of users.

    Returns: a dictionary mapping usernames to (key_id, key_secret)
    """
    aws_user: Optional[str] = None
    aws_key_id: Optional[str] = None
    aws_secret: Optional[str] = None
    user_creds: Dict[str, Tuple[str, str]] = dict()

    logging.info("Searching Terraform state for IAM credentials.")
    for aws_user, aws_key_id, aws_secret in parse_creds(terraform_state):
        logging.info(f"Found credentials for user: {aws_user}")
        user_creds[aws_user] = (aws_key_id, aws_secret)

    if len(user_creds) == 0:
        logging.warning("No users found.")
    return user_creds


def get_resource_secrets(terraform_state: Dict) -> Dict[str, str]:
    """Collect secrets from tagged Terraform resources."""
    secrets: Dict[str, str] = dict()
    logging.info("Searching Terraform state for tagged resources.")
    for secret_name, secret_value in parse_tagged_resources(terraform_state):
        logging.info(f"Found secret: {secret_name}")
        secrets[secret_name] = secret_value
    for secret_name, secret_value in parse_tagged_outputs(terraform_state):
        logging.info(f"Found secret: {secret_name}")
        secrets[secret_name] = secret_value
    return secrets


def create_user_secrets(user_creds: Dict[str, Tuple[str, str]]) -> Dict[str, str]:
    """Create secrets for user key IDs and key values."""
    secrets: Dict[str, str] = dict()
    for user_name, creds in user_creds.items():
        # If there is more than one user add the name as a suffix
        if len(user_creds) > 1:
            # Convert the username into an environment variable-safe form
            suffix = ("_" + re.sub(r"\W", "_", user_name)).upper()
        else:
            suffix = ""
        secrets["AWS_ACCESS_KEY_ID" + suffix] = creds[0]
        secrets["AWS_SECRET_ACCESS_KEY" + suffix] = creds[1]
    return secrets


def create_all_secrets(
    secrets: Dict[str, str], github_token: str, repo_name: str, dry_run: bool = False
) -> None:
    """Log into GitHub and create all encrypted secrets."""
    logging.info("Creating GitHub API session using personal access token.")
    session: requests.Session = requests.Session()
    session.auth = ("", github_token)

    # Get the repo's public key to be used to encrypt secrets
    public_key: Dict[str, str] = get_public_key(session, repo_name)

    for secret_name, secret_value in secrets.items():
        if dry_run:
            logging.info(f"Would create secret {secret_name}")
        else:
            set_secret(session, repo_name, secret_name, secret_value, public_key)


def main() -> int:
    """Set up logging and call the requested commands."""
    args: Dict[str, Any] = docopt.docopt(__doc__, version="1.1.0")

    # Validate and convert arguments as needed
    schema: Schema = Schema(
        {
            "<github-personal-access-token>": Or(
                None,
                And(
                    str,
                    lambda n: len(n) == 40,
                    error="--token must be a 40 character personal access token.",
                ),
            ),
            "--log-level": And(
                str,
                Use(str.lower),
                lambda n: n in ("debug", "info", "warning", "error", "critical"),
                error="Possible values for --log-level are "
                "debug, info, warning, error, and critical.",
            ),
            "--repo": Or(
                None,
                And(
                    str,
                    lambda n: "/" in n,
                    error='Repository names must contain a "/"',
                ),
            ),
            "--token": Or(
                None,
                And(
                    str,
                    lambda n: len(n) == 40,
                    error="--token must be a 40 character personal access token.",
                ),
            ),
            str: object,  # Don't care about other keys, if any
        }
    )

    try:
        validated_args: Dict[str, Any] = schema.validate(args)
    except SchemaError as err:
        # Exit because one or more of the arguments were invalid
        print(err, file=sys.stderr)
        return 1

    # Assign validated arguments to variables
    dry_run: bool = validated_args["--dry-run"]
    github_token_to_save: str = validated_args["<github-personal-access-token>"]
    log_level: str = validated_args["--log-level"]
    repo_name: str = validated_args["--repo"]
    state_filename: str = validated_args["--state"]
    github_token: str = validated_args["--token"]

    # Set up logging
    logging.basicConfig(
        format="%(asctime)-15s %(levelname)s %(message)s", level=log_level.upper()
    )

    # Just save the GitHub token to the keyring and exit.
    if validated_args["save"]:
        logging.info("Saving the GitHub personal access token to the keyring.")
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, github_token_to_save)
        logging.info("Success!")
        return 0

    # If the user does not provide a repo name we'll try to determine it from git
    if not repo_name:
        repo_name = get_repo_name()
    logging.info(f"Using GitHub repository name: {repo_name}")

    if github_token is None:
        logging.debug("GitHub token not provided in arguments.  Checking keyring.")
        github_token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if github_token is None:
            logging.critical(
                "GitHub token not provided on command line or found in keychain."
            )
            return -1
        else:
            logging.info("GitHub token retrieved from keyring.")

    # Get the state from Terraform or a json file
    terraform_state: Dict = get_terraform_state(state_filename)

    # Users mapped to their (key, secret)
    user_creds: Dict[str, Tuple[str, str]] = get_users(terraform_state)

    # User secrets created from credentials.  Names mapped to value.
    user_secrets: Dict[str, str] = create_user_secrets(user_creds)

    # Secrets created from tagged resources. Names mapped to value.
    resource_secrets: Dict[str, str] = get_resource_secrets(terraform_state)

    # Check if there are overlaps in the keys.
    if not user_secrets.keys().isdisjoint(resource_secrets.keys()):
        logging.warning("User secret names overlap with resource secret names.")

    # Merge the two dictionaries together
    all_secrets: Dict[str, str] = resource_secrets.copy()
    all_secrets.update(user_secrets)

    # All the ducks are in a row, let's do this thang!
    create_all_secrets(all_secrets, github_token, repo_name, dry_run)

    logging.info("Success!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
