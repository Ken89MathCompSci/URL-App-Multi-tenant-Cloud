variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name, used as a prefix for all resource names"
  type        = string
  default     = "url-shortener"
}

variable "image_tag" {
  description = "Docker image tag to deploy (e.g. git SHA or 'latest')"
  type        = string
  default     = "latest"
}

variable "container_port" {
  description = "Port the container listens on"
  type        = number
  default     = 8000
}
