"""Utility functions for interacting with GitHub."""

# Standard Python Libraries
from base64 import b64encode
import logging
import re
import subprocess  # nosec : security implications have been considered
from typing import Dict, Tuple

# Third-Party Libraries
from nacl import encoding, public
import requests

# Constants
GIT_URL_RE: re.Pattern = re.compile(
    r"^(?:git@|https://)github\.com[:/](.*?)(?:\.git)?$"
)


def encrypt(public_key: str, secret_value: str) -> str:
    """Encrypt a Unicode string using the public key."""
    public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
    sealed_box = public.SealedBox(public_key)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")


def get_public_key(session: requests.Session, repo_name) -> Dict[str, str]:
    """Fetch the public key for a repository."""
    logging.info("Requesting public key for repository %s", repo_name)
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
    logging.info("Creating secret %s", secret_name)
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
        repo_name: str = match.groups()[0]
    else:
        logging.critical("Could not determine GitHub repository name.")
        logging.critical("Use the --repo option to specify it manually.")
        raise Exception("Could not determine GitHub repository name.")
    return repo_name


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
            logging.info("Would create secret %s", secret_name)
        else:
            set_secret(session, repo_name, secret_name, secret_value, public_key)
