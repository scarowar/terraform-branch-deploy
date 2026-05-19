# Environment Variables

Trigger mode writes `TF_BD_*` variables to `GITHUB_ENV`. Later steps in the same job can use them directly.

## Variables

| Variable | Description |
| --- | --- |
| `TF_BD_CONTINUE` | `true` when the workflow should continue. |
| `TF_BD_ENVIRONMENT` | Target environment. |
| `TF_BD_OPERATION` | `plan`, `apply`, or `rollback`. |
| `TF_BD_IS_ROLLBACK` | `true` for rollback commands. |
| `TF_BD_SHA` | Commit SHA associated with the command. |
| `TF_BD_REF` | Git ref to check out before execute mode. |
| `TF_BD_ACTOR` | User who triggered the command. |
| `TF_BD_PR_NUMBER` | Pull request number. |
| `TF_BD_PARAMS` | Extra command arguments after the separator. |
| `TF_BD_DEPLOYMENT_ID` | GitHub deployment ID. |
| `TF_BD_COMMENT_ID` | Triggering comment ID. |
| `TF_BD_INITIAL_REACTION_ID` | Initial reaction ID used for cleanup. |
| `TF_BD_NOOP` | `true` for plan operations. |
| `TF_BD_TYPE` | Branch Deploy command type. |

## Gate Later Steps

Every step after trigger mode should check `TF_BD_CONTINUE`:

```yaml
- uses: actions/checkout@v6
  if: env.TF_BD_CONTINUE == 'true'
  with:
    ref: ${{ env.TF_BD_REF }}
```

If `TF_BD_CONTINUE` is not `true`, the command was not authorized, was not a supported command, or did not require execution.

## Choose Credentials by Environment

Use `TF_BD_ENVIRONMENT` to choose cloud credentials:

```yaml
- uses: aws-actions/configure-aws-credentials@v5
  if: env.TF_BD_CONTINUE == 'true' && env.TF_BD_ENVIRONMENT == 'prod'
  with:
    role-to-assume: arn:aws:iam::123456789012:role/prod-terraform
    aws-region: us-east-1
```

## Detect Rollbacks

```yaml
- name: Notify rollback
  if: env.TF_BD_IS_ROLLBACK == 'true'
  run: echo "Rollback requested for $TF_BD_ENVIRONMENT"
```

## Job Boundary

`GITHUB_ENV` variables are scoped to one job. Keep trigger mode, credential setup, and execute mode in the same job.
