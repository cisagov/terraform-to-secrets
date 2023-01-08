"""Utility functions for interacting with the Terraform state."""

# Standard Python Libraries
import json
import logging
import subprocess  # nosec : security implications have been considered
from typing import Dict, Generator, Optional, Tuple, Union

# Constants
GITHUB_SECRET_NAME_TAG: str = "GitHub_Secret_Name"
GITHUB_SECRET_TERRAFORM_LOOKUP_TAG: str = "GitHub_Secret_Terraform_Lookup"


def get_terraform_state(filename: str = "") -> Dict:
    """Retrieve IAM credentials from Terraform state.

    Returns the Terraform state as a dict.
    """
    data: Union[str, bytes, bytearray]
    if filename:
        logging.info("Reading state from json file %s", filename)
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
            "Found %s on %s with value %s",
            GITHUB_SECRET_NAME_TAG,
            resource_name,
            secret_name,
        )
        if lookup_tag:
            logging.debug(
                "Found %s on %s with value %s",
                GITHUB_SECRET_TERRAFORM_LOOKUP_TAG,
                resource_name,
                lookup_tag,
            )
            secret_value = resource_data.get(lookup_tag)
            if secret_value is None:
                logging.warning("Could not lookup value with key %s", lookup_tag)
            else:
                logging.debug("Looked up value: %s", secret_value)
                yield secret_name, secret_value
        else:
            logging.warning(
                "Missing %s on %s.", GITHUB_SECRET_TERRAFORM_LOOKUP_TAG, resource_name
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
        logging.info("Found credentials for user: %s", aws_user)
        user_creds[aws_user] = (aws_key_id, aws_secret)

    if len(user_creds) == 0:
        logging.warning("No users found.")
    return user_creds


def get_resource_secrets(terraform_state: Dict) -> Dict[str, str]:
    """Collect secrets from tagged Terraform resources."""
    secrets: Dict[str, str] = dict()
    logging.info("Searching Terraform state for tagged resources.")
    for secret_name, secret_value in parse_tagged_resources(terraform_state):
        logging.info("Found secret: %s", secret_name)
        secrets[secret_name] = secret_value
    for secret_name, secret_value in parse_tagged_outputs(terraform_state):
        logging.info("Found secret: %s", secret_name)
        secrets[secret_name] = secret_value
    return secrets
