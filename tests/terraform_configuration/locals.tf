# Get the current account
data "aws_caller_identity" "current" {
}

locals {
  account_ids                = []
  aws_region                 = "us-east-2"
  entity_name                = "terraform-to-docs"
  gh_parameter_description   = "A test value that should be converted to a GitHub Secret."
  gh_parameter_name          = "/testing/terraform-to-secrets/github_secret"
  gh_parameter_value         = "THIS-VALUE-IS-A-GITHUB-SECRET"
  gh_user_name               = format("gh-%s", local.entity_name)
  global_tags                = {}
  iam_usernames              = [local.gh_user_name, local.tf_user_name]
  iam_usernames_formatted    = formatlist("user/%s", local.iam_usernames)
  policy_description         = format(local.policy_description_fstring, local.entity_name)
  policy_description_fstring = "Allows read-only access to SSM Parameter Store parameters required for %s."
  policy_name                = substr(format(local.policy_name_fstring, local.entity_name), 0, 64)
  policy_name_fstring        = "ParameterStoreReadOnly-%s"
  role_description           = format("A role that can be assumed to allow for CI testing of %s.", local.entity_name)
  role_max_session_duration  = 3600
  role_name                  = format("Test-%s", local.entity_name)
  tf_parameter_description   = "A test value that should not be converted to a GitHub Secret."
  tf_parameter_name          = "/testing/terraform-to-secrets/terraform_secret"
  tf_parameter_value         = "THIS-VALUE-IS-NOT-A-GITHUB-SECRET"
  tf_user_name               = format("tf-%s", local.entity_name)
}
