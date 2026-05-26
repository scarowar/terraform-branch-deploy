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

- Public docs should use `scarowar/terraform-branch-deploy@<terraform-branch-deploy-ref>` in reusable examples and explain that users must choose a reviewed release tag, full commit SHA, or intentionally moving major tag.
- For release validation, use the exact candidate SHA or release tag in the external E2E repository.
- Do not use floating `main` for release validation or production examples.

## Security Gates

Before tagging:

- Review open security advisories.
- Review Dependabot alerts.
- Review code scanning alerts.
- Review secret scanning alerts.
- Review SonarQube Cloud findings.
- Resolve every open finding, regardless of severity, or record a narrow false-positive decision.
- Confirm the stable branch is protected by branch protection or a repository ruleset.
- Confirm CODEOWNERS is active for maintainer-owned workflow and action changes.
- Confirm required checks include CI, Security, CodeQL, SonarQube, Dependency Review, docs build, and an external E2E run for action runtime changes.

Scanner policy must not be relaxed for a release.

## Branch Deploy Compatibility

- Keep `github/branch-deploy` pinned by full commit SHA.
- Update Branch Deploy only in a dedicated change.
- Before updating Branch Deploy, compare upstream inputs, outputs, command behavior, and release notes against the pinned version.
- Update contract tests in the same change as any Branch Deploy compatibility change.
- Re-run local gates and the external E2E suite after any action runtime change.

## External E2E Gate

Run the external E2E suite against the exact candidate SHA or release tag. Do not validate a release from a floating `main` reference.

For pull request validation, comment `/e2e` after the code has been reviewed. The dispatch workflow resolves the exact pull request head SHA and runs the external E2E workflow in the test repository. Live PRs, comments, locks, and workflow runs belong in the test repository.

Confirm `TFBD_E2E_DISPATCH_TOKEN` is configured in this repository and `TFBD_STATUS_TOKEN` is configured in the test repository.

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
- Keep docs and maintainer instructions short, canonical, and non-duplicative.
- Draft release notes from `CHANGELOG.md` and the tag diff. Keep them factual and user-facing.
- Keep public commands, outputs, environment variables, plan naming, cache keys, and rollback behavior stable unless a test proves they are wrong.
- Normal apply must use a saved `.tfplan` file.
- Direct apply without a saved plan is reserved for rollback.
