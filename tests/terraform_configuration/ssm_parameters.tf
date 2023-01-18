resource "aws_ssm_parameter" "gh_secret" {
  description = local.gh_parameter_description
  name        = local.gh_parameter_name
  type        = "SecureString"
  value       = local.gh_parameter_value

  tags = {
    "GitHub_Secret_Name"             = "SECRET_VALUE",
    "GitHub_Secret_Terraform_Lookup" = "arn"
  }
}

resource "aws_ssm_parameter" "tf_secret" {
  description = local.tf_parameter_description
  name        = local.tf_parameter_name
  type        = "SecureString"
  value       = local.tf_parameter_value
}
