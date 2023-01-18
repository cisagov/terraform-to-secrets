provider "aws" {
  region = local.aws_region

  default_tags {
    tags = local.global_tags
  }
}
