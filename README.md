
# Terraform Branch Deploy

![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/scarowar/terraform-branch-deploy/badge)](https://scorecard.dev/viewer/?uri=github.com/scarowar/terraform-branch-deploy)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=scarowar_terraform-branch-deploy&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=scarowar_terraform-branch-deploy)
![CodeQL](https://github.com/scarowar/terraform-branch-deploy/actions/workflows/codeql.yml/badge.svg)
![Dependabot](https://img.shields.io/badge/dependabot-enabled-brightgreen?logo=dependabot)
[![pre-commit.ci status](https://results.pre-commit.ci/badge/github/scarowar/terraform-branch-deploy/main.svg)](https://results.pre-commit.ci/latest/github/scarowar/terraform-branch-deploy/main)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/images/cover-dark.png">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/images/cover-light.png">
  <img alt="Terraform Branch Deploy Cover" src="docs/assets/images/cover-light.png">
</picture>

<p align="center">
  <b><a href="https://scarowar.github.io/terraform-branch-deploy/">📖 Documentation (GitHub Pages)</a></b>
</p>


## 📝 Overview

Terraform Branch Deploy extends [branch-deploy](https://github.com/github/branch-deploy) with first-class support for Terraform infrastructure automation.

## ⭐ Key Features

- **PR-driven automation**: Trigger `plan` and `apply` by commenting on pull requests.
- **Environment targeting**: Define environments (dev, staging, prod, etc.) in `.tf-branch-deploy.yml` with per-environment config, var files, and working directories.
- **Safe deployments**: Preview every change with a Terraform plan before apply, and support instant rollbacks to a stable branch.
- **Environment locking**: Prevent concurrent or conflicting deployments with automatic and manual environment locks.
- **Custom arguments**: Pass extra Terraform CLI arguments from PR comments and fine-tune behavior per environment or globally via `.tf-branch-deploy.yml`.
- **Enterprise ready**: Works with GitHub Enterprise Server (GHES) and public GitHub, with automated GHES release tagging.
- **Workflow integration**: Use the `skip` input to extract environment context for advanced, multi-step workflows without running Terraform operations.

## 📸 See It In Action

Watch Terraform Branch Deploy in action - from comment to Terraform infrastructure deployment:

[Terraform Branch Deploy Demo](https://github.com/user-attachments/assets/15b1c060-9be5-4203-9c5d-caa088c2535d)

---

## 📃 License

MIT License - see [LICENSE](https://github.com/scarowar/terraform-branch-deploy/blob/main/LICENSE) for details.

---

## 🔗 Quick Links

- [Documentation site](https://scarowar.github.io/terraform-branch-deploy/)
- [GitHub Discussions](https://github.com/scarowar/terraform-branch-deploy/discussions)
- [Report a bug](https://github.com/scarowar/terraform-branch-deploy/issues)
- [Security policy](https://github.com/scarowar/terraform-branch-deploy/blob/main/SECURITY.md)
- [Contributing guide](https://github.com/scarowar/terraform-branch-deploy/blob/main/CONTRIBUTING.md)
- [License](https://github.com/scarowar/terraform-branch-deploy/blob/main/LICENSE)
