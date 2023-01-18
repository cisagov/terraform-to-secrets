# IAM policy document that allows assumption of the ParameterStoreReadOnly
# role for these users
data "aws_iam_policy_document" "assume_parameterstorereadonly_role_doc" {
  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRole",
      "sts:TagSession",
    ]

    resources = [
      aws_iam_role.ssm_role.arn,
    ]
  }
}

# The IAM policy allowing this user to assume their custom
# ParameterStoreReadOnly role
resource "aws_iam_user_policy" "gh_assume_parameterstorereadonly" {
  name   = "GitHub-Assume${aws_iam_role.ssm_role.name}"
  policy = data.aws_iam_policy_document.assume_parameterstorereadonly_role_doc.json
  user   = aws_iam_user.gh_user.name
}

# The IAM policy allowing this user to assume their custom
# ParameterStoreReadOnly role
resource "aws_iam_user_policy" "tf_assume_parameterstorereadonly" {
  name   = "Terraform-Assume${aws_iam_role.ssm_role.name}"
  policy = data.aws_iam_policy_document.assume_parameterstorereadonly_role_doc.json
  user   = aws_iam_user.tf_user.name
}
