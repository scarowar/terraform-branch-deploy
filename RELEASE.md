# Maintainer Release Checklist

Terraform Branch Deploy wraps `github/branch-deploy` and adds Terraform execution. A release must preserve the public command flow, action inputs and outputs, `TF_BD_*` environment variables, and saved plan behavior.

## Local Gates

Run from this repository:

```bash
uv run pytest
uv run pre-commit run --all-files
uv run zensical build --strict --clean
```

Do not release if action inputs, outputs, commands, or docs are out of sync.

## Version References

- Update `docs/includes/version.txt` to the candidate release tag.
- Run `scripts/update-version.sh`.
- Confirm every public Terraform Branch Deploy action example points at the same candidate tag.

## Security Gates

Before tagging:

- Review open security advisories.
- Review Dependabot alerts.
- Review code scanning alerts.
- Review secret scanning alerts.
- Resolve high and critical alerts, or record why they do not affect the release artifact.
- Confirm the stable branch is protected by branch protection or a repository ruleset.

## Branch Deploy Compatibility

- Keep `github/branch-deploy` pinned by full commit SHA.
- Update Branch Deploy only in a dedicated change.
- Before updating Branch Deploy, compare upstream inputs, outputs, command behavior, and release notes against the pinned version.
- Update contract tests in the same change as any Branch Deploy compatibility change.
- Re-run local gates and the external E2E suite after any action runtime change.

## External E2E Gate

Run the external E2E suite against the exact candidate SHA or release tag. Do not validate a release from a floating `main` reference.

Watch these flows explicitly:

- Plan, review, and apply the saved plan.
- Targeted plan followed by plain apply.
- Plan invalidation after new commits.
- Lock, unlock, and lock status.
- Rollback with `.apply main to <env>`.
- Extra Terraform plan arguments after the command separator.
- Branch Deploy output compatibility.

## Release Discipline

- Add a regression test for every critical bug fix.
- Keep release changes small and directly tested.
- Keep public commands, outputs, environment variables, plan naming, cache keys, and rollback behavior stable unless a test proves they are wrong.
- Normal apply must use a saved `.tfplan` file.
- Direct apply without a saved plan is reserved for rollback.
