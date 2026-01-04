# Test Terraform Branch Deploy

This repository is used for E2E testing of `terraform-branch-deploy`.

## Usage

1. Create a PR
2. Comment `.plan to dev` or `.apply to prod`
3. Observe the workflow running

## Environments

- `dev` - Development environment
- `prod` - Production environment

## File Structure

```
terraform/
├── dev/
│   ├── main.tf
│   └── dev.tfvars
├── prod/
│   ├── main.tf
│   └── prod.tfvars
└── common.tfvars
```
