resource "aws_iam_role" "gh_ci" {
  assume_role_policy   = data.aws_iam_policy_document.assume_role_doc.json
  description          = local.role_description
  max_session_duration = local.role_max_session_duration
  name                 = "GitHub-${local.role_name}"

  tags = {
    "GitHub_Secret_Name"             = "TEST_ROLE_TO_ASSUME",
    "GitHub_Secret_Terraform_Lookup" = "arn"
  }
}

resource "aws_iam_role" "tf_ci" {
  assume_role_policy   = data.aws_iam_policy_document.assume_role_doc.json
  description          = local.role_description
  max_session_duration = local.role_max_session_duration
  name                 = "Terraform-${local.role_name}"
}

# Attach the AWS SSM Parameter Store read role policies to the CI roles
resource "aws_iam_role_policy_attachment" "gh_ssm_attachment" {
  policy_arn = aws_iam_policy.ssm_policy.arn
  role       = aws_iam_role.gh_ci.name
}

resource "aws_iam_role_policy_attachment" "tf_ssm_attachment" {
  policy_arn = aws_iam_policy.ssm_policy.arn
  role       = aws_iam_role.tf_ci.name
}
