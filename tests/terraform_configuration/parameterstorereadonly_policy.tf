# IAM policy document that that allows for reading the SSM parameter
data "aws_iam_policy_document" "ssm_doc" {
  statement {
    effect = "Allow"

    actions = [
      "ssm:GetParameters",
      "ssm:GetParameter"
    ]

    resources = [
      aws_ssm_parameter.gh_secret.arn,
      aws_ssm_parameter.tf_secret.arn,
    ]
  }
}

# The IAM policy for our ssm-reading role
resource "aws_iam_policy" "ssm_policy" {
  description = local.policy_description
  name        = local.policy_name
  policy      = data.aws_iam_policy_document.ssm_doc.json
}
