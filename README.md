
# Terraform Branch Deploy 🚀

![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/scarowar/terraform-branch-deploy/badge)](https://scorecard.dev/viewer/?uri=github.com/scarowar/terraform-branch-deploy)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=scarowar_terraform-branch-deploy&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=scarowar_terraform-branch-deploy)
![CodeQL](https://github.com/scarowar/terraform-branch-deploy/actions/workflows/codeql.yml/badge.svg)
![Dependabot](https://img.shields.io/badge/dependabot-enabled-brightgreen?logo=dependabot)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/scarowar/terraform-branch-deploy/main.svg)](https://results.pre-commit.ci/latest/github/scarowar/terraform-branch-deploy/main)

**terraform-branch-deploy** brings the power of [IssueOps](https://issue-ops.github.io/docs/) to your infrastructure. Simply comment `.plan to <env>` and `.apply to <env>` on any pull request to preview and deploy Terraform changes to a specific environment—keeping your main branch stable and always deployable.

## ✨ Why You'll Love It

- **🗨️ ChatOps Magic**: Deploy infrastructure with simple PR comments like `.plan to <env>` and `.apply to <env>`
- **🛡️ Safety First**: Test changes in real environments before they hit your main branch
- **🌍 Multi-Environment**: Deploy to dev, staging, prod with environment-specific configurations
- **🔒 Smart Locking**: Prevent conflicting deployments with automatic environment locks
- **🏢 Enterprise Ready**: Full GitHub Enterprise Server (GHES) compatibility with automated releases
- **⚙️ Highly Configurable**: Fine-tune everything with a simple YAML configuration file

## 🎮 Quick Commands

| Command | What it does |
|---------|-------------|
| `.plan to <env>` | Preview changes for a specific environment (e.g., dev, staging, prod) |
| `.apply to <env>` | Deploy changes to a specific environment |
| `.plan to staging` | Preview changes for staging environment |
| `.apply to staging` | Deploy changes to staging environment |
| `.apply main to prod` | Rollback prod to main branch (emergency) |
| `.lock` | Lock an environment to prevent deployments |
| `.unlock` | Release environment lock |
| `.wcid` | "Where Can I Deploy?" - show lock status |

> **Pro tip**: Add extra Terraform arguments with a pipe: `.plan | -var=debug=true`
> **Note:** By default, naked commands like `.plan` and `.apply` without an environment are blocked for safety. Use `.plan to dev` or `.apply to prod` instead. You can allow naked commands by setting `disable_naked_commands: false` in your workflow.

## 📸 See It In Action

Watch terraform-branch-deploy in action - from comment to infrastructure deployment:

[Terraform Branch Deploy Demo](https://github.com/user-attachments/assets/15b1c060-9be5-4203-9c5d-caa088c2535d)

## 🚀 Getting Started

Ready to deploy infrastructure like a pro? Here's your 3-step setup:

### Prerequisites

Before you begin, make sure you have:
- A GitHub repository with Terraform configuration files
- Appropriate cloud provider credentials (AWS, Azure, GCP, etc.)
- GitHub repository permissions for Actions and Deployments

### Step 1: Create Your Workflow

Create `.github/workflows/terraform-deploy.yml` in your repository:

```yaml
name: "Terraform Branch Deploy"

on:
  issue_comment:
    types: [created]

permissions:
  pull-requests: write
  deployments: write
  contents: write
  checks: read
  statuses: read

jobs:
  terraform_deployment:
    if: ${{ github.event.issue.pull_request }}
    runs-on: ubuntu-latest

    steps:
      # Add your cloud authentication here (AWS, Azure, GCP, etc.)

      - name: terraform-branch-deploy
        uses: scarowar/terraform-branch-deploy@v0.1.0
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

### Step 2: Configure Your Environments

Create `.tf-branch-deploy.yml` in your repository root:

```yaml
# yaml-language-server: $schema=./tf-branch-deploy.schema.json

default-environment: dev

production-environments:
  - prod

defaults:
  var-files:
    paths:
      - common.tfvars
  plan-args:
    args:
      - "-compact-warnings"

environments:
  dev:
    working-directory: ./terraform/dev
    var-files:
      paths:
        - ./terraform/dev/dev.tfvars

  prod:
    working-directory: ./terraform/prod
    var-files:
      inherit: false  # Don't inherit common.tfvars
      paths:
        - ./terraform/prod/prod.tfvars
        - ./terraform/prod/secrets.tfvars
```

### Step 3: Deploy


Comment on any pull request to deploy your changes (environment targeting required by default):

- **`.plan to dev`** → Preview what changes will be made in the dev environment
- **`.apply to dev`** → Deploy the changes to the dev environment
- **`.apply main to prod`** → Emergency rollback to main branch in prod


## 🧠 How It Works

terraform-branch-deploy follows the **[branch deployment](https://github.com/marketplace/actions/branch-deploy#about-)** pattern - a battle-tested approach that keeps your main branch stable:

### The Branch Deployment Philosophy

- **🎯 Main is Sacred**: Your main branch is always stable and deployable
- **🔬 Test Before Merge**: Deploy and test infrastructure changes from feature branches
- **🚨 Easy Rollbacks**: Emergency? Deploy main branch to rollback instantly
- **🔍 Preview Everything**: See exactly what will change before applying

### Under the Hood

1. **Comment**: You comment `.plan to dev` on a PR
2. **Validate**: Action validates Terraform syntax and formatting
3. **Plan**: Terraform plan runs and posts results as PR comment
4. **Apply**: Comment `.apply to dev` to deploy the planned changes
5. **Track**: GitHub deployment status tracks your infrastructure state

This approach eliminates the dreaded "merge → deploy → break → scramble" cycle that plagues traditional workflows.

## ⚙️ Configuration

### Action Inputs

| Input | Description | Default | Example |
|-------|-------------|---------|---------|
| `github-token` | GitHub token with required permissions | - | `${{ secrets.GITHUB_TOKEN }}` |
| `terraform-version` | Terraform CLI version to use | `latest` | `1.7.5` |
| `working-directory` | Default path to Terraform files | `.` | `infrastructure/` |
| `noop-trigger` | Command for plan operations | `.plan` | `.preview` |
| `trigger` | Command for apply operations | `.apply` | `.deploy` |
| `stable_branch` | Branch for rollback operations | `main` | `master` |
| `skip` | Extract environment info and exit early | `false` | `true` |
| `admins` | Comma-separated list of admin users/teams | `false` | `monalisa,octocat,my-org/my-team` |
| `admins_pat` | Personal access token for org team access | `false` | `${{ secrets.ADMIN_PAT }}` |
| `disable_naked_commands` | Require users to specify an environment when using IssueOps commands (e.g., `.plan to dev` instead of just `.plan`). When set to `true` (default), commands without an environment are blocked for safety. | `true` | `false` |

### Action Outputs

| Output    | Description |
|-----------|-------------|
| `env`     | The environment that has been selected for deployment |
| `continue`| The string "true" if the deployment should continue, otherwise empty – use this to conditionally control whether your deployment should proceed |
| `sha`     | The sha of the branch to be deployed |
| `rollback`| The string "true" if the deployment is a rollback operation, otherwise "false" |
| `plan`    | The string "true" if the deployment is a plan operation, otherwise "false" |
| `apply`   | The string "true" if the deployment is an apply operation, otherwise "false" |
| `params`  | The raw parameters that were passed into the deployment command |
| `parsed_params` | A stringified JSON object of the parsed parameters that were passed into the deployment command |

### Enterprise Support

🏢 **GitHub Enterprise Server (GHES) Users**: We automatically create GHES-compatible releases with every new version. Look for releases tagged with `-ghes` suffix (e.g., `v0.1.0-ghes`) which use compatible action versions.

## 💡 Advanced Features

### Environment Inheritance
Configure defaults once, override per environment:

```yaml
defaults:
  plan-args:
    args: ["-compact-warnings"]

environments:
  prod:
    plan-args:
      inherit: false  # Don't inherit defaults
      args: ["-parallelism=30"]
```

### Dynamic Arguments
Pass extra Terraform arguments via comments:

```bash
.plan to dev | -var=debug=true -target=module.api
.apply to dev | -auto-approve=false
```

### Smart Locking
Prevent deployment conflicts:

```bash
.lock prod --reason "Maintenance window"
.unlock prod
.wcid prod  # "Where Can I Deploy?"
```


## 🆘 Need Help?

- 💬 **Questions?** Start a [discussion](https://github.com/scarowar/terraform-branch-deploy/discussions)
- 🐛 **Found a bug?** Open an [issue](https://github.com/scarowar/terraform-branch-deploy/issues)
- 🔒 **Security concern?** See our [security policy](./SECURITY.md)

## 🤝 Contributing

We'd love your help making terraform-branch-deploy even better! Check out our [contributing guide](./CONTRIBUTING.md) to get started.

## 📄 License

MIT License - see [LICENSE](./LICENSE) for details.

## 🙏 Credits

Built with ❤️ and ☕ on top of these amazing projects:
- [branch-deploy](https://github.com/github/branch-deploy) - The IssueOps foundation
- [tfcmt](https://github.com/suzuki-shunsuke/tfcmt) - Beautiful Terraform PR comments
- [IssueOps](https://issue-ops.github.io/docs/) - ChatOps for GitHub Actions

---

**Ready to deploy infrastructure like a pro? ⭐ this repo and give it a try!**
