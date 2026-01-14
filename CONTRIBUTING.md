# Contributing to terraform-branch-deploy

Thank you for your interest in contributing to terraform-branch-deploy! Your ideas, bug reports, and improvements are welcome. Please read this guide to help you get started.

## How to Contribute

- **Bug Reports & Feature Requests:**
  - Open an issue on [GitHub Issues](https://github.com/scarowar/terraform-branch-deploy/issues).
  - Provide as much detail as possible, including steps to reproduce bugs or a clear description of your feature request.

- **Pull Requests:**
  1. Fork the repository and create your branch from `main`.
  2. Make clear, focused changes. Each pull request should address a single concern.
  3. If your change affects the action's behavior, update the documentation (e.g., `README.md`).
  4. Run all pre-commit checks before submitting:
     ```sh
     pre-commit run --all-files
     ```
  5. Open a pull request and describe your changes clearly.

## Code Style & Linting

- Python code is formatted and linted with [Ruff](https://docs.astral.sh/ruff/).
- Pre-commit hooks are configured. Please run `pre-commit install` after cloning the repository to enable automatic checks before each commit.
- You can manually run all pre-commit checks with:
  ```sh
  pre-commit run --all-files
  ```
- YAML and GitHub Actions workflows are also checked via pre-commit.

## Security

- Please do not report security vulnerabilities in public issues. See [SECURITY.md](./SECURITY.md) for how to report vulnerabilities.

## Code of Conduct

- By participating, you agree to follow our [Code of Conduct](./CODE_OF_CONDUCT.md).

## Questions & Discussions

- For general questions, ideas, or discussions, please use [GitHub Discussions](https://github.com/scarowar/terraform-branch-deploy/discussions).

---

Thank you for helping make terraform-branch-deploy better!
