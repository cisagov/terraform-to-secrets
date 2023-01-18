# IAM policy document that allows assumption of the GitHub CI role
data "aws_iam_policy_document" "gh_assume_ci_role_doc" {
  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRole",
      "sts:TagSession",
    ]

    resources = [
      aws_iam_role.gh_ci.arn,
    ]
  }
}

# The IAM policy that allows assumption of the CI role
resource "aws_iam_user_policy" "gh_assume_ci_role" {
  name   = "GitHub-Assume${aws_iam_role.gh_ci.name}"
  policy = data.aws_iam_policy_document.gh_assume_ci_role_doc.json
  user   = aws_iam_user.gh_user.name
}

# IAM policy document that allows assumption of the Terraform CI role
data "aws_iam_policy_document" "tf_assume_ci_role_doc" {
  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRole",
      "sts:TagSession",
    ]

    resources = [
      aws_iam_role.tf_ci.arn,
    ]
  }
}

# The IAM policy that allows assumption of the CI role
resource "aws_iam_user_policy" "tf_assume_ci_role" {
  name   = "Terraform-Assume${aws_iam_role.tf_ci.name}"
  policy = data.aws_iam_policy_document.tf_assume_ci_role_doc.json
  user   = aws_iam_user.tf_user.name
}
