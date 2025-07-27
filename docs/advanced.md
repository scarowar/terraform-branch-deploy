# Advanced Workflows

Take your automation further with advanced patterns, skip mode, and real-world workflow examples.

## Using Skip Mode for Composable Workflows

Skip mode lets you extract environment and parameter info from PR comments—without running any Terraform operations. This is ideal for:

- Injecting environment-specific secrets
- Running pre-checks or conditional logic
- Chaining multiple actions in a single workflow

**How to use skip mode:**

```yaml title="Workflow step: Extract environment info only"
- name: Extract environment info
	id: extract-env
	uses: scarowar/terraform-branch-deploy@v0.1.0
	with:
		github-token: ${{ secrets.GITHUB_TOKEN }}
		skip: true

- name: Use environment info
	run: echo "Target environment is ${{ steps.extract-env.outputs.env }}"
```

**Available outputs:**

| Output           | Description                                 |
|------------------|---------------------------------------------|
| `env`            | The selected environment (e.g., dev, prod)  |
| `params`         | Raw parameters from the command             |
| `parsed_params`  | JSON object of parsed parameters            |
| `continue`       | "true" if deployment should proceed         |

## Advanced Workflow Examples

### Injecting Secrets Based on Environment

```yaml title="Inject secrets for production"
- name: Extract environment info
	id: extract-env
	uses: scarowar/terraform-branch-deploy@v0.1.0
	with:
		github-token: ${{ secrets.GITHUB_TOKEN }}
		skip: true

- name: Inject production secrets
	if: ${{ steps.extract-env.outputs.env == 'prod' }}
	run: echo "Injecting production secrets..."
```

### Conditional Steps for Staging

```yaml title="Run staging-specific checks"
- name: Extract environment info
	id: extract-env
	uses: scarowar/terraform-branch-deploy@v0.1.0
	with:
		github-token: ${{ secrets.GITHUB_TOKEN }}
		skip: true

- name: Run staging checks
	if: ${{ steps.extract-env.outputs.env == 'staging' }}
	run: echo "Running staging-specific checks"
```

### Multi-Step Workflow with Skip Mode

You can chain steps using outputs from skip mode to build complex, environment-aware workflows.

```yaml title="Composable multi-step workflow"
- name: Extract environment info
	id: extract-env
	uses: scarowar/terraform-branch-deploy@v0.1.0
	with:
		github-token: ${{ secrets.GITHUB_TOKEN }}
		skip: true

- name: Pre-deployment validation
	run: |
		echo "Validating for ${{ steps.extract-env.outputs.env }}"
		# Add custom validation logic here

- name: Deploy if allowed
	if: ${{ steps.extract-env.outputs.continue == 'true' }}
	uses: scarowar/terraform-branch-deploy@v0.1.0
	with:
		github-token: ${{ secrets.GITHUB_TOKEN }}
```

---

See [Configuration](configuration.md) for all options, or [Commands](commands.md) for the full command reference.
