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
import logging
import sys
from typing import Any, Dict, Tuple

# Third-Party Libraries
import docopt
import keyring
from schema import And, Or, Schema, SchemaError, Use

from ._version import __version__
from .github import create_all_secrets, create_user_secrets, get_repo_name
from .terraform import get_resource_secrets, get_terraform_state, get_users

# Constants
KEYRING_SERVICE = "terraform-to-secrets"
KEYRING_USERNAME = "GitHub PAT"


def main() -> None:
    """Set up logging and call the requested commands."""
    args: Dict[str, Any] = docopt.docopt(__doc__, version=__version__)

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
        sys.exit(1)

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
        return

    # If the user does not provide a repo name we'll try to determine it from git
    if not repo_name:
        repo_name = get_repo_name()
    logging.info("Using GitHub repository name: %s", repo_name)

    if github_token is None:
        logging.debug("GitHub token not provided in arguments.  Checking keyring.")
        github_token = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if github_token is None:
            logging.critical(
                "GitHub token not provided on command line or found in keychain."
            )
            sys.exit(-1)
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
