# The GitHub IAM user being created
resource "aws_iam_user" "gh_user" {
  name = local.gh_user_name

  tags = {
    "GitHub_Secret_Name"             = "TEST_USER",
    "GitHub_Secret_Terraform_Lookup" = "arn"
  }
}

# The IAM access key for the GitHub user
resource "aws_iam_access_key" "gh_key" {
  user = aws_iam_user.gh_user.name
}

# The Terraform IAM user being created
resource "aws_iam_user" "tf_user" {
  name = local.tf_user_name
}

# The IAM access key for the Terraform user
resource "aws_iam_access_key" "tf_key" {
  user = aws_iam_user.tf_user.name
}
