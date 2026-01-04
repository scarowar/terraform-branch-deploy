# Simple Terraform config for E2E testing
# Uses local backend (no cloud resources needed)

terraform {
  required_version = ">= 1.0.0"

  # Local file backend - no cloud credentials needed
  backend "local" {}
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "message" {
  description = "A test message"
  type        = string
  default     = "Hello from terraform-branch-deploy"
}

resource "local_file" "test" {
  content  = "Environment: ${var.environment}\nMessage: ${var.message}"
  filename = "${path.module}/output.txt"
}

output "environment" {
  value = var.environment
}

output "file_path" {
  value = local_file.test.filename
}
