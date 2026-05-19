# Outputs

Outputs mirror the trigger state from Branch Deploy and the Terraform execution result from execute mode.

## Trigger State Outputs

These outputs are available from the trigger-mode step.

| Output | Description |
| --- | --- |
| `continue` | `true` when the workflow should continue. |
| `triggered` | `true` when a supported command was detected. |
| `environment` | Target environment. |
| `operation` | Derived operation: `plan`, `apply`, or `rollback`. |
| `is-rollback` | `true` for rollback commands. |
| `sha` | Commit SHA associated with the command. |
| `ref` | Git ref to check out before execute mode. |
| `noop` | `true` for plan operations. |
| `actor` | User who triggered the command. |
| `params` | Extra command arguments after the separator. |
| `comment-id` | Triggering comment ID. |
| `deployment-id` | GitHub deployment ID. |
| `initial-reaction-id` | Initial reaction ID used during lifecycle cleanup. |
| `type` | Branch Deploy command type. |
| `issue-number` | Pull request or issue number. |

## Execute Outputs

These outputs are available from the execute-mode step.

| Output | Description |
| --- | --- |
| `working-directory` | Resolved Terraform working directory. |
| `var-files` | JSON array of variable files. |
| `is-production` | `true` when the target environment is production. |
| `plan-file` | Path to the plan file created during plan. |
| `plan-checksum` | SHA-256 checksum of the plan file. |
| `has-changes` | `true` when the plan contains changes. |

## Example

```yaml
- uses: scarowar/terraform-branch-deploy@v0
  id: trigger
  with:
    mode: trigger
    github-token: ${{ secrets.GITHUB_TOKEN }}

- uses: actions/checkout@v6
  if: steps.trigger.outputs.continue == 'true'
  with:
    ref: ${{ steps.trigger.outputs.ref }}

- uses: scarowar/terraform-branch-deploy@v0
  id: execute
  if: steps.trigger.outputs.continue == 'true'
  with:
    mode: execute
    github-token: ${{ secrets.GITHUB_TOKEN }}

- name: Notify when Terraform changed infrastructure
  if: steps.execute.outputs.has-changes == 'true'
  run: echo "Terraform reported changes"
```

For steps in the same job, prefer `TF_BD_*` environment variables after trigger mode. They are the primary contract used by execute mode.
