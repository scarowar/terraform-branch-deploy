# Environment Variables

Trigger mode exports environment variables prefixed with `TF_BD_` for use in subsequent workflow steps.

---

## Available Variables

| Variable | Description |
|----------|-------------|
| `TF_BD_CONTINUE` | `true` if workflow should proceed |
| `TF_BD_ENVIRONMENT` | Target environment name |
| `TF_BD_OPERATION` | `plan`, `apply`, or `rollback` |
| `TF_BD_IS_ROLLBACK` | `true` if this is a rollback |
| `TF_BD_SHA` | Commit SHA to deploy |
| `TF_BD_REF` | Git ref to checkout |
| `TF_BD_ACTOR` | User who triggered deployment |
| `TF_BD_PR_NUMBER` | PR number |
| `TF_BD_PARAMS` | Extra parameters from command |
| `TF_BD_DEPLOYMENT_ID` | GitHub deployment ID |
| `TF_BD_COMMENT_ID` | Triggering comment ID |
| `TF_BD_NOOP` | `true` for plan operations |

---

## Conditional Execution

Use `TF_BD_CONTINUE` to gate subsequent steps:

```yaml
- uses: actions/checkout@v4
  if: env.TF_BD_CONTINUE == 'true'
  with:
    ref: ${{ env.TF_BD_REF }}
```

When `TF_BD_CONTINUE` is `false`:

- The comment was not a recognized command
- The user lacks permission
- The environment is locked by another user
- An error occurred during parsing

---

## Environment-Specific Logic

Use `TF_BD_ENVIRONMENT` to vary behavior:

```yaml
- name: Assume Role
  if: env.TF_BD_CONTINUE == 'true'
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::${{ env.TF_BD_ENVIRONMENT == 'prod' && '111111111111' || '222222222222' }}:role/deploy
    aws-region: us-east-1
```

---

## Rollback Detection

Use `TF_BD_IS_ROLLBACK` to detect rollback operations:

```yaml
- name: Notify on Rollback
  if: env.TF_BD_IS_ROLLBACK == 'true'
  run: |
    echo "ROLLBACK IN PROGRESS: $TF_BD_ENVIRONMENT"
```
