#!/usr/bin/env pytest -vs
"""Tests for the terraform_to_secrets.github module."""
# Standard Python Libraries
from base64 import b64decode

# Third-Party Libraries
from nacl import encoding, public
import pytest

# cisagov Libraries
import terraform_to_secrets.github

test_plaintext = "Hello, World!"

repository_name = "cisagov/terraform-to-secrets"

test_single_user_secrets = {
    "test-user": (" AKIAIOSFODNN7TEST", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYTESTKEY")
}
test_multiple_user_secrets = {
    "example-user": (
        "AKIAIOSFODNN7EXAMPLE",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    ),
    "test-user": ("AKIAIOSFODNN7TEST", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYTESTKEY"),
}


@pytest.fixture(scope="session")
def encryption_keys():
    """Generate the private and corresponding public key to use for testing."""
    test_key_private = public.PrivateKey.generate()
    test_key_public = test_key_private.public_key
    return (test_key_public, test_key_private)


def test_encrypt(encryption_keys):
    """Verify that a test value is correctly encrypted and Base 64 encoded."""
    encrypted_value = terraform_to_secrets.github.encrypt(
        encryption_keys[0].encode(encoding.Base64Encoder).decode("utf-8"),
        test_plaintext,
    )
    unseal_box = public.SealedBox(encryption_keys[1])
    plaintext_value = unseal_box.decrypt(b64decode(encrypted_value)).decode("utf-8")
    assert plaintext_value == test_plaintext


def test_get_repo_name():
    """Verify that the current repository name is returned."""
    repo_name = terraform_to_secrets.github.get_repo_name()
    assert repo_name == repository_name, "expected repository name not found"


def test_create_user_secrets_single_user():
    """Verify that the secrets for a single user are created."""
    created_secrets = terraform_to_secrets.github.create_user_secrets(
        test_single_user_secrets
    )
    assert len(created_secrets.keys()) == 2, "incorrect number of secrets created"
    assert (
        "AWS_ACCESS_KEY_ID" in created_secrets.keys()
    ), "missing expected key AWS_ACCESS_KEY_ID"
    assert (
        created_secrets["AWS_ACCESS_KEY_ID"] == test_single_user_secrets["test-user"][0]
    ), "value for AWS_ACCESS_KEY_ID does not match test value"
    assert (
        "AWS_SECRET_ACCESS_KEY" in created_secrets.keys()
    ), "missing expected key AWS_SECRET_ACCESS_KEY"
    assert (
        created_secrets["AWS_SECRET_ACCESS_KEY"]
        == test_single_user_secrets["test-user"][1]
    ), "value for AWS_SECRET_ACCESS_KEY does not match test value"


def test_create_user_secrets_multiple_users():
    """Verify that the secrets for multiple users are created."""
    created_secrets = terraform_to_secrets.github.create_user_secrets(
        test_multiple_user_secrets
    )
    assert len(created_secrets.keys()) == 4, "incorrect number of secrets created"
    for suffix, test_key in [
        ("_EXAMPLE_USER", "example-user"),
        ("_TEST_USER", "test-user"),
    ]:
        assert (
            f"AWS_ACCESS_KEY_ID{suffix}" in created_secrets.keys()
        ), f"missing expected key AWS_ACCESS_KEY_ID{suffix}"
        assert (
            created_secrets[f"AWS_ACCESS_KEY_ID{suffix}"]
            == test_multiple_user_secrets[test_key][0]
        ), f"value for AWS_ACCESS_KEY_ID{suffix} does not match test value"
        assert (
            f"AWS_SECRET_ACCESS_KEY{suffix}" in created_secrets.keys()
        ), f"missing expected key AWS_SECRET_ACCESS_KEY{suffix}"
        assert (
            created_secrets[f"AWS_SECRET_ACCESS_KEY{suffix}"]
            == test_multiple_user_secrets[test_key][1]
        ), f"value for AWS_SECRET_ACCESS_KEY{suffix} does not match test value"
