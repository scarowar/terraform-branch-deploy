# Test Terraform Branch Deploy

This repository contains E2E tests for `terraform-branch-deploy`.

## Workflows

| Workflow | Description | Test Command |
|----------|-------------|--------------|
| [1-basic-deploy.yml](.github/workflows/1-basic-deploy.yml) | One-step deployment | `.plan to dev` |
| [2-advanced-deploy.yml](.github/workflows/2-advanced-deploy.yml) | Two-step with prep work | `.plan to dev` |
| [3-enterprise-deploy.yml](.github/workflows/3-enterprise-deploy.yml) | Execute mode (full control) | `.plan to dev` |

## Testing Instructions

### 1. Setup

```bash
# Copy this folder to your test repo
cp -r test-repo-setup/* /path/to/test-tf-branch-deploy/
cd /path/to/test-tf-branch-deploy/
git add .
git commit -m "Add test workflows"
git push
```

### 2. Create a Test Branch

```bash
git checkout -b test/v0.2.0
# Make a small change to trigger plan
echo 'message = "Testing v0.2.0"' >> terraform/dev/dev.tfvars
git add .
git commit -m "test: trigger deployment"
git push -u origin test/v0.2.0
```

### 3. Create a PR

Create a PR from `test/v0.2.0` to `main`.

### 4. Test Commands

Comment on the PR to test:

| Test Case | Command | Expected Result |
|-----------|---------|-----------------|
| Plan to dev | `.plan to dev` | ✅ Plan runs |
| Apply to dev | `.apply to dev` | ✅ Apply runs |
| Plan to prod | `.plan to prod` | ✅ Production warning |
| Invalid env | `.plan to foo` | ❌ Error message |
| Lock environment | `.lock dev` | 🔒 Lock created |
| Unlock | `.unlock dev` | 🔓 Lock released |
| Help | `.help` | 📖 Help message |

## Environments

| Environment | Working Dir | Production |
|-------------|-------------|------------|
| dev | `terraform/dev` | No |
| prod | `terraform/prod` | Yes |

## Terraform Config

Uses the `local_file` provider - no cloud credentials needed.
Creates a simple text file as output.
