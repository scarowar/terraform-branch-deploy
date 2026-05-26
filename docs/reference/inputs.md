# Inputs

All inputs for `scarowar/terraform-branch-deploy`.

## Required Inputs

| Input | Description |
| --- | --- |
| `mode` | `trigger` parses the PR comment and exports state. `execute` runs Terraform from that state. |
| `github-token` | Token with the permissions needed for comments, deployments, checks, and repository access. |

## Input Ownership

Terraform Branch Deploy has two kinds of inputs:

- Terraform execution inputs, used by execute mode to find configuration and run Terraform.
- Branch Deploy pass-through inputs, used by trigger mode to configure command parsing, authorization, checks, locks, and deployment policy.

Execute mode reads the `TF_BD_*` state exported by trigger mode. Do not call execute mode directly.

## Terraform Execution Inputs

| Input | Default | Description |
| --- | --- | --- |
| `config-path` | `.tf-branch-deploy.yml` | Path to the Terraform Branch Deploy configuration file. |
| `terraform-version` | `latest` | Terraform CLI version used in execute mode. A matching preinstalled Terraform binary is reused when possible. |
| `dry-run` | `false` | Print Terraform commands in execute mode without running Terraform. Trigger-mode and earlier workflow steps can still run. |

## Branch Deploy Command Inputs

These inputs are passed to Branch Deploy in trigger mode.

| Input | Default | Description |
| --- | --- | --- |
| `trigger` | `.apply` | Apply command trigger. |
| `noop-trigger` | `.plan` | Plan command trigger. |
| `lock-trigger` | `.lock` | Lock command trigger. |
| `unlock-trigger` | `.unlock` | Unlock command trigger. |
| `help-trigger` | `.help` | Help command trigger. |
| `lock-info-alias` | `.wcid` | Current-lock status command. |
| `param-separator` | <code>&#124;</code> | Separator before extra Terraform arguments. |

## Environments

| Input | Default | Description |
| --- | --- | --- |
| `environment-targets` | auto-detected | Comma-separated deployable environments. Empty means read from `.tf-branch-deploy.yml`. |
| `production-environments` | auto-detected | Comma-separated production environments. Empty means read from `.tf-branch-deploy.yml`. |
| `environment-urls` | empty | Branch Deploy environment URL mapping. |
| `draft-permitted-targets` | empty | Environments that allow draft PR deployments. |

## Branch and Rollback

| Input | Default | Description |
| --- | --- | --- |
| `stable-branch` | `main` | Branch Deploy stable branch input used by rollback commands such as `.apply main to prod`. Set this on trigger mode when the rollback source is not `main`. |
| `update-branch` | `warn` | How Branch Deploy handles outdated branches: `disabled`, `warn`, or `force`. |
| `outdated-mode` | `strict` | Branch Deploy outdated-branch policy. |
| `allow-sha-deployments` | `false` | Allow deployment of explicit commit SHAs. |
| `allow-non-default-target-branch` | `false` | Allow PRs targeting non-default branches to deploy. |

## Review, Checks, and Permissions

| Input | Default | Description |
| --- | --- | --- |
| `checks` | `all` | Check policy before deployment. |
| `ignored-checks` | empty | Checks ignored by Branch Deploy. |
| `skip-ci` | empty | Environments where CI checks are skipped. |
| `skip-reviews` | empty | Environments where review checks are skipped. |
| `required-contexts` | empty | Explicit required status contexts. |
| `permissions` | `write,admin` | Repository permission levels allowed to deploy. |
| `admins` | `false` | Users or teams allowed to bypass review requirements. |
| `admins-pat` | `false` | PAT used for GitHub team membership lookup. |
| `commit-verification` | `false` | Require verified commits. |
| `disable-naked-commands` | `false` | Require commands to include `to <env>`. |
| `deployment-confirmation` | `false` | Require deployment confirmation. |
| `deployment-confirmation-timeout` | `300` | Confirmation timeout in seconds. |
| `use-security-warnings` | `true` | Show Branch Deploy security warnings. |

## Deployment Order and Locks

| Input | Default | Description |
| --- | --- | --- |
| `enforced-deployment-order` | empty | Required environment promotion order, such as `dev,staging,prod`. |
| `global-lock-flag` | `--global` | Flag used for global lock commands. |
| `sticky-locks` | `false` | Keep locks after deployments complete. |
| `sticky-locks-for-noop` | `false` | Keep locks after plan commands. |

## Comments and Reactions

| Input | Default | Description |
| --- | --- | --- |
| `reaction` | `eyes` | Initial reaction added to the trigger comment. |

## Branch Deploy Inputs Not Exposed

Terraform Branch Deploy exposes the Branch Deploy inputs listed above. Other Branch Deploy inputs are outside this action's public interface.

Forked pull request execution and Branch Deploy's alternate merge workflows are not enabled by this action.

If you are upgrading from v0.1.0 or an older pinned commit, see [Upgrading](../upgrading.md) before changing workflow inputs.

## Minimal Example

```yaml
- uses: scarowar/terraform-branch-deploy@<terraform-branch-deploy-ref>
  with:
    mode: trigger
    github-token: ${{ secrets.GITHUB_TOKEN }}
    disable-naked-commands: true
    checks: all
    outdated-mode: strict
```
