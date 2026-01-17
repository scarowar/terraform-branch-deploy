# Lifecycle Hooks

Run custom commands at specific points in the Terraform execution lifecycle.

## Hook Phases

```
pre-init → terraform init → post-init → pre-plan → terraform → post-plan/post-apply
```

| Phase | When | Use Cases |
|-------|------|-----------|
| `pre-init` | Before terraform init | Security scanning, secrets detection |
| `post-init` | After terraform init | Provider validation |
| `pre-plan` | Before terraform plan/apply | Linting, policy checks |
| `post-plan` | After terraform plan | Cost estimation, change review |
| `post-apply` | After terraform apply | CMDB updates, documentation |

## Built-in Hooks

v0.2.0 includes curated built-in hooks with structured output:

| Hook | Default | Phase | Description |
|------|---------|-------|-------------|
| `terraform validate` | **ON** | pre-plan | Configuration validation |
| `trivy` | off | pre-init | Security vulnerability scanning |
| `gitleaks` | off | pre-init | Secrets detection |
| `tflint` | off | pre-plan | Terraform linting |
| `infracost` | off | post-plan | Cost estimation |
| `terraform-docs` | off | post-apply | Documentation generation |

> [!NOTE]
> `terraform validate` runs by default. All other hooks are opt-in.

## Custom Hooks

Define custom hooks in `.tf-branch-deploy.yml`:

```yaml
hooks:
  pre-init:
    - name: "Security Scan"
      run: trivy fs --security-checks vuln,secret .
      fail-on-error: true
      timeout: 300
    
    - name: "Secrets Detection"
      run: gitleaks detect --source . --no-git
      fail-on-error: true
  
  pre-plan:
    - name: "TFLint"
      run: tflint --config .tflint.hcl
    
    - name: "Checkov"
      run: checkov -d . --framework terraform
      fail-on-error: false  # Warn but don't block
  
  post-plan:
    - name: "Cost Estimation"
      run: infracost diff --path .
      condition: plan-only
  
  post-apply:
    - name: "Generate Docs"
      run: terraform-docs markdown . > README.md
      condition: apply-only
```

## Hook Properties

| Property | Default | Description |
|----------|---------|-------------|
| `name` | *required* | Human-readable hook name |
| `run` | *required* | Shell command to execute |
| `fail-on-error` | `true` | Block deployment on non-zero exit |
| `timeout` | `600` | Maximum seconds before kill |
| `condition` | `always` | When to run (see below) |
| `working-directory` | terraform dir | Override working directory |
| `env` | | Additional environment variables |

## Conditions

| Condition | Runs on |
|-----------|---------|
| `always` | plan, apply, rollback |
| `plan-only` | plan only |
| `apply-only` | apply and rollback |
| `rollback-only` | rollback only |

## Environment Variables

All hooks have access to `TF_BD_*` variables:

| Variable | Description |
|----------|-------------|
| `TF_BD_PHASE` | Current phase (pre-init, post-apply, etc.) |
| `TF_BD_ENVIRONMENT` | Target environment |
| `TF_BD_OPERATION` | plan, apply, or rollback |
| `TF_BD_IS_ROLLBACK` | true/false |
| `TF_BD_SHA` | Commit SHA |
| `TF_BD_REF` | Branch ref |
| `TF_BD_ACTOR` | User who triggered |
| `TF_BD_PR_NUMBER` | Pull request number |
| `TF_BD_PARAMS` | Extra args from command |
| `TF_BD_WORKING_DIR` | Terraform working directory |
| `TF_BD_IS_PRODUCTION` | true/false |

Post-plan hooks also receive:
- `TF_BD_PLAN_FILE` — Path to plan file
- `TF_BD_HAS_CHANGES` — true/false

## Examples

### Security Scanning with Trivy

```yaml
hooks:
  pre-init:
    - name: "Trivy Security Scan"
      run: |
        trivy fs . \
          --security-checks vuln,secret,config \
          --exit-code 1 \
          --severity HIGH,CRITICAL
```

### Policy Enforcement with OPA

```yaml
hooks:
  pre-plan:
    - name: "OPA Policy Check"
      run: |
        terraform plan -out=tfplan.bin
        terraform show -json tfplan.bin > tfplan.json
        opa eval --data policies/ --input tfplan.json 'data.terraform.deny[_]'
```

### Cost Estimation with Infracost

```yaml
hooks:
  post-plan:
    - name: "Infracost"
      run: infracost diff --path . --format json --out-file infracost.json
      condition: plan-only
```

### CMDB Update on Deploy

```yaml
hooks:
  post-apply:
    - name: "Update CMDB"
      run: |
        curl -X POST "https://cmdb.example.com/api/deployments" \
          -H "Authorization: Bearer $CMDB_TOKEN" \
          -d "{\"environment\": \"$TF_BD_ENVIRONMENT\", \"sha\": \"$TF_BD_SHA\"}"
      condition: apply-only
      env:
        CMDB_TOKEN: ${{ secrets.CMDB_TOKEN }}
```

## Fail-on-Error Behavior

| `fail-on-error` | Exit Code | Result |
|-----------------|-----------|--------|
| `true` (default) | 0 | Continue |
| `true` | non-zero | **Block deployment** |
| `false` | 0 | Continue |
| `false` | non-zero | Warn and continue |

## Timeout Behavior

Hooks are killed after `timeout` seconds:

```yaml
hooks:
  pre-init:
    - name: "Long Running Scan"
      run: ./slow-scan.sh
      timeout: 900  # 15 minutes
```

Default timeout is 600 seconds (10 minutes).
