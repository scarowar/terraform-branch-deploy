# Outputs

Values exported by the execute mode for use in subsequent workflow steps.

---

## Execute Mode Outputs

| Output | Description |
|--------|-------------|
| `working-directory` | Resolved Terraform working directory |
| `var-files` | JSON array of var files |
| `is-production` | `true` if production environment |
| `plan-file` | Path to generated plan file |
| `plan-checksum` | SHA256 of plan file |
| `has-changes` | `true` if plan has changes |

---

## Usage

Access outputs using `steps.<id>.outputs`:

```yaml
- uses: scarowar/terraform-branch-deploy@v0.2.0
  id: execute
  if: env.TF_BD_CONTINUE == 'true'
  with:
    mode: execute
    github-token: ${{ secrets.GITHUB_TOKEN }}

- name: Check for changes
  if: steps.execute.outputs.has-changes == 'true'
  run: echo "Infrastructure changes detected"
```

---

## Using Outputs in Subsequent Jobs

To use outputs in a different job, export them at the job level:

```yaml
jobs:
  deploy:
    runs-on: ubuntu-latest
    outputs:
      has-changes: ${{ steps.execute.outputs.has-changes }}
    steps:
      - uses: scarowar/terraform-branch-deploy@v0.2.0
        id: execute
        # ...

  notify:
    needs: deploy
    if: needs.deploy.outputs.has-changes == 'true'
    runs-on: ubuntu-latest
    steps:
      - run: echo "Changes were deployed"
```
