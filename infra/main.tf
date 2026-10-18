terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state — uncomment and fill in bucket/key/table before first use.
  # Remove this block entirely to use local state for development.
  #
  # backend "s3" {
  #   bucket         = "your-tf-state-bucket"
  #   key            = "url-shortener/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "your-tf-lock-table"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = var.app_name
      ManagedBy = "Terraform"
    }
  }
}
