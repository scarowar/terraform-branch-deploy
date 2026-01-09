# Troubleshooting

## Common Issues

### "No plan file found for this SHA"

**Cause:** You tried to `.apply` without running `.plan` first, or the SHA changed.

**Fix:** Run `.plan to <env>` first. If you made new commits, plan again.

### "Environment not found"

**Cause:** The environment in your command doesn't exist in `.tf-branch-deploy.yml`.

**Fix:** Check your config file. Environment names are case-sensitive.

### "Config file not found"

**Cause:** `.tf-branch-deploy.yml` doesn't exist in the repository root.

**Fix:** Create the config file or use `config-path` input to specify location.

### Plan Output Not Appearing in PR

**Cause:** `tfcmt` is not installed or GitHub token lacks permissions.

**Fix:** The action installs `tfcmt` automatically. Ensure your token has `pull-requests: write`.

### "Permission denied" Errors

**Cause:** GitHub token missing required permissions.

**Fix:** Add to your workflow:

```yaml
permissions:
  contents: write
  pull-requests: write
  deployments: write
```

### Pre-Terraform Hook Fails

**Cause:** Hook script exited with non-zero code.

**Fix:** Check the script. Use `set -e` to fail on first error:

```yaml
pre-terraform-hook: |
  set -e
  ./scripts/build.sh
```

### Environment Lock Stuck

**Cause:** Previous deployment failed without releasing lock.

**Fix:** Comment `.unlock <env>` on any open PR.

### Cache Not Found

**Cause:** Plan cache expired or different SHA.

**Fix:** 
- GitHub Actions cache expires after 7 days of no access
- New commits = new SHA = new cache needed
- Run `.plan` again

## Debug Mode

Add to your workflow for verbose output:

```yaml
env:
  ACTIONS_STEP_DEBUG: true
```

## Getting Help

- [GitHub Issues](https://github.com/scarowar/terraform-branch-deploy/issues)
- [GitHub Discussions](https://github.com/scarowar/terraform-branch-deploy/discussions)
