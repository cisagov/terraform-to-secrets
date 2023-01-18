output "gh_access_key" {
  description = "The IAM access key associated with the GitHub CI IAM user."
  sensitive   = true
  value       = aws_iam_access_key.gh_key
}

output "tf_access_key" {
  description = "The IAM access key associated with the Terraform CI IAM user."
  sensitive   = true
  value       = aws_iam_access_key.tf_key
}

output "gh_ci_role" {
  value       = aws_iam_role.gh_ci
  description = "The IAM role that the CI users can assume to do what it needs to do in the production account."
}

output "tf_ci_role" {
  value       = aws_iam_role.tf_ci
  description = "The IAM role that the CI users can assume to do what it needs to do in the production account."
}

output "gh_user" {
  value       = aws_iam_user.gh_user
  description = "The GitHub CI IAM user."
}

output "tf_user" {
  value       = aws_iam_user.tf_user
  description = "The Terraform CI IAM user."
}

output "ssm_policy" {
  description = "The IAM policy that can read the specified SSM Parameter Store parameters."
  value       = aws_iam_policy.ssm_policy
}

output "ssm_role" {
  description = "The IAM role that can read the specified SSM Parameter Store parameters."
  value       = aws_iam_role.ssm_role
}
