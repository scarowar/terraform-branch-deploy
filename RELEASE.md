# Release Checklist

This project wraps `github/branch-deploy` and adds Terraform execution around it. Releases must preserve the public command flow, action inputs and outputs, and `TF_BD_*` environment contract.

## Required Checks

Run these checks from this repository:

```bash
uv run pytest
pre-commit run --all-files
```

Run the external E2E suite from `~/dev/scarowar/test-terraform-branch-deploy` against the exact candidate SHA or release tag:

```bash
uv run pytest tests/e2e/ -v --tb=long
```

Do not certify a release from a floating `main` reference.

## Compatibility Rules

- Keep branch-deploy pinned by full commit SHA.
- Update branch-deploy only in a dedicated change.
- Before updating branch-deploy, compare upstream inputs, outputs, runtime, and release notes against the pinned version.
- Update contract tests in the same change as any branch-deploy version change.
- Re-run the full local and E2E gates after any action runtime change.

## Stability Rules

- Add a regression test for every release-blocking bug fix.
- Avoid unrelated refactors in release-candidate fixes.
- Keep public commands, outputs, environment variables, plan naming, cache keys, and rollback behavior stable unless a test proves they are wrong.
- Normal apply must use a cached `.tfplan` file and matching `.meta.json` sidecar.
- Direct apply without a saved plan is allowed only for rollback.
- Prefer small changes with direct tests over broad rewrites.
