# Contributing

Thanks for helping improve Terraform Branch Deploy. Keep changes focused, tested, and easy to review.

## Issues

Use GitHub Issues for reproducible bugs and concrete feature requests. Include:

- The command comment that triggered the workflow.
- A sanitized workflow file.
- A sanitized `.tf-branch-deploy.yml`.
- Relevant workflow logs.
- The action version or commit SHA.

Do not report security vulnerabilities in public issues. See [SECURITY.md](SECURITY.md).

## Pull Requests

1. Create a branch from `main`.
2. Keep the pull request focused on one behavior or documentation topic.
3. Update tests when behavior changes.
4. Update docs when public commands, inputs, outputs, config, or safety behavior changes.
5. Run the local checks before opening the pull request.

## Local Checks

```bash
uv run pytest
uv run pre-commit run --all-files
uv run zensical build --strict --clean
```

## Documentation

Docs are user-facing. Keep them simple, direct, and focused on how to operate the action safely.

Prefer text, command examples, and small diagrams for workflow explanation. Avoid screenshots or demo videos unless they are real, reviewed, maintained, and clearly better than a diagram.

Preview the docs locally:

```bash
uv run zensical serve
```

## Code Style

- Python is formatted and linted with Ruff.
- Type checks run with mypy through pre-commit.
- Security and workflow checks run through pre-commit.
- Keep action runtime changes small and covered by tests.

## Branch Deploy Compatibility

This project wraps `github/branch-deploy`. Keep that dependency pinned by full commit SHA. Update it only in a dedicated change that includes compatibility review, contract test updates if needed, and full local plus E2E validation.

## Conduct

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
