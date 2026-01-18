"""
Terraform Branch Deploy CLI.

Typer-based CLI for Terraform infrastructure deployments via GitHub PRs.

Three modes:
- parse: Read config, output environment settings
- trigger: [For action.yml] Parse command, export TF_BD_* env vars, STOP
- execute: [For action.yml] Run terraform with lifecycle completion
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from .config import EnvironmentConfig, TerraformBranchDeployConfig
    from .executor import TerraformExecutor

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_config

DEFAULT_CONFIG_PATH = Path(".tf-branch-deploy.yml")
GITHUB_URL_DEFAULT = "https://github.com"
ACTIONS_RUNS_PATH = "/actions/runs/"

app = typer.Typer(
    name="tf-branch-deploy",
    help="ChatOps for Terraform infrastructure deployments via GitHub PRs.",
    no_args_is_help=True,
)
console = Console()


class Mode(str, Enum):
    """Execution mode for action.yml."""

    TRIGGER = "trigger"  # Parse command, export TF_BD_* env vars, STOP
    EXECUTE = "execute"  # Run terraform with lifecycle completion


def set_github_output(name: str, value: str) -> None:
    """Set a GitHub Actions output."""
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with open(output_file, "a") as f:
            if "\n" in value:
                import uuid

                delimiter = uuid.uuid4().hex
                f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")
            else:
                f.write(f"{name}={value}\n")
    console.print(f"[dim]Output: {name}={value[:50]}{'...' if len(value) > 50 else ''}[/dim]")


def format_error_for_comment(
    message: str,
    details: str | None = None,
    suggestion: str | None = None,
    logs_url: str | None = None,
) -> str:
    """Format a professional error message for GitHub comment.
    
    Matches branch-deploy's clean, seamless style:
    - No subtitles or section headers
    - Clear explanation in natural paragraph flow
    - Optional details as bullet points or inline code
    - Suggestion in blockquote format
    - Logs link when applicable
    
    Args:
        message: Main explanation paragraph
        details: Optional additional details (can include markdown)
        suggestion: Optional suggestion shown in blockquote
        logs_url: Optional link to workflow logs
    
    Returns:
        Formatted markdown string for the comment
    """
    lines = [message]
    
    if details:
        lines.append("")
        lines.append(details)
    
    if logs_url:
        lines.append("")
        lines.append(f"📋 [View workflow logs]({logs_url})")
    
    if suggestion:
        lines.append("")
        lines.append(f"> {suggestion}")
    
    return "\n".join(lines)


def _parse_extra_args(raw: str) -> list[str]:
    """Parse extra args string into list, handling shell quoting.

    When users write commands like:
        .plan to dev | -var='msg=hello world'

    The quotes are meant for SHELL protection (to preserve spaces).
    But since we now bypass shell (set env var directly), we need to:
    1. Split on unquoted spaces
    2. Strip the outer shell quotes from values
    3. Preserve internal quotes like -target=module.test["key"]

    Examples:
        "-var='msg=hello world'" -> ['-var=msg=hello world']
        "-var='key=value'" -> ['-var=key=value']
        "-target=module.test[\"key\"]" -> ['-target=module.test["key"]']
        "-refresh=false -parallelism=5" -> ['-refresh=false', '-parallelism=5']
    """
    tokenizer = _ArgTokenizer()
    tokens = tokenizer.tokenize(raw)
    return [_strip_shell_quotes(arg) for arg in tokens]


class _ArgTokenizer:
    """Tokenizer for shell-quoted argument strings."""

    def __init__(self) -> None:
        self.args: list[str] = []
        self.current: list[str] = []
        self.in_single = False
        self.in_double = False
        self.in_bracket = 0

    def tokenize(self, raw: str) -> list[str]:
        """Tokenize a raw argument string into individual args."""
        for char in raw:
            self._process_char(char)
        self._flush_current()
        return self.args

    def _process_char(self, char: str) -> None:
        """Process a single character."""
        if char == "'" and not self.in_double:
            self.in_single = not self.in_single
            self.current.append(char)
        elif char == '"' and not self.in_single:
            self.in_double = not self.in_double
            self.current.append(char)
        elif char == "[" and not self._in_quotes():
            self.in_bracket += 1
            self.current.append(char)
        elif char == "]" and not self._in_quotes():
            self.in_bracket = max(0, self.in_bracket - 1)
            self.current.append(char)
        elif char == " " and not self._in_quotes() and self.in_bracket == 0:
            self._flush_current()
        else:
            self.current.append(char)

    def _in_quotes(self) -> bool:
        """Check if currently inside quotes."""
        return self.in_single or self.in_double

    def _flush_current(self) -> None:
        """Flush current token to args list."""
        if self.current:
            self.args.append("".join(self.current))
            self.current = []


def _strip_shell_quotes(arg: str) -> str:
    """Strip shell quoting from an argument value.

    Handles patterns like:
        -var='key=value' -> -var=key=value
        -var="key=value" -> -var=key=value
        -var='msg=hello world' -> -var=msg=hello world
        -target=module.test["key"] -> -target=module.test["key"] (preserve inner quotes)
    """
    eq_pos = arg.find("=")
    if eq_pos == -1:
        return arg

    flag = arg[: eq_pos + 1]
    value = arg[eq_pos + 1 :]

    if len(value) >= 2 and (
        (value.startswith("'") and value.endswith("'"))
        or (value.startswith('"') and value.endswith('"'))
    ):
        value = value[1:-1]

    return flag + value





def _load_and_validate_config(
    config_path: Path, environment: str
) -> tuple["TerraformBranchDeployConfig", "EnvironmentConfig"]:
    """Load and validate config, returning config and environment config."""
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] Invalid config: {e}")
        raise typer.Exit(1) from None

    if environment not in config.environments:
        console.print(f"[red]Error:[/red] Environment '{environment}' not found")
        raise typer.Exit(1)

    return config, config.get_environment(environment)


@app.command(name="get-config")
def get_config(
    key: Annotated[str, typer.Argument(help="Config key to retrieve (default-environment or production-environments)")],
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to .tf-branch-deploy.yml")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """
    Retrieve a value from the configuration file.
    
    Replaces yq usage in action.yml for robust, dependency-free config parsing.
    """
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] Invalid config: {e}")
        raise typer.Exit(1) from None

    if key == "default-environment":
        print(config.default_environment)
    elif key == "production-environments":
        print(",".join(config.production_environments))
    else:
        console.print(f"[red]Error:[/red] Unsupported key: {key}")
        raise typer.Exit(1)


@app.command(name="complete-lifecycle")
def complete_lifecycle(
    status: Annotated[str, typer.Option(help="Execution status (success/failure)")],
    failure_reason: Annotated[str | None, typer.Option(help="Reason for failure if status is failure")] = None,
) -> None:
    """Complete the deployment lifecycle (update status, reactions, comments)."""
    from .lifecycle import LifecycleManager

    # Gather context from env vars
    env_vars = dict(os.environ)
    repo = env_vars.get("GH_REPO") or env_vars.get("GITHUB_REPOSITORY")
    token = env_vars.get("GITHUB_TOKEN")
    
    if not repo or not token:
        console.print("[red]Error:[/red] GITHUB_REPOSITORY or GITHUB_TOKEN not set")
        raise typer.Exit(1)

    manager = LifecycleManager(repo=repo, github_token=token)

    # 1. Update deployment status
    deployment_id = env_vars.get("TF_BD_DEPLOYMENT_ID")
    environment = env_vars.get("TF_BD_ENVIRONMENT")
    if deployment_id and environment:
        manager.update_deployment_status(deployment_id, status, environment)

    # 2. Remove initial reaction
    comment_id = env_vars.get("TF_BD_COMMENT_ID")
    reaction_id = env_vars.get("TF_BD_INITIAL_REACTION_ID")
    if comment_id and reaction_id:
        manager.remove_reaction(comment_id, reaction_id)

    # 3. Add result reaction
    reaction = "rocket" if status == "success" else "-1"
    if comment_id:
        manager.add_reaction(comment_id, reaction)

    # 4. Post result comment
    pr_number = env_vars.get("TF_BD_PR_NUMBER")
    if pr_number:
        body = manager.format_result_comment(status, env_vars, failure_reason)
        manager.post_result_comment(pr_number, body)
    
    # 5. Remove non-sticky lock
    if environment:
        manager.remove_non_sticky_lock(environment)
    
    console.print("\n[green]✅ Lifecycle complete[/green]")


@app.command()
def execute(
    environment: Annotated[str, typer.Option("--environment", "-e", help="Target environment")],
    operation: Annotated[str, typer.Option("--operation", "-o", help="plan or apply")],
    sha: Annotated[str, typer.Option("--sha", "-s", help="Git commit SHA")],
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to .tf-branch-deploy.yml")
    ] = DEFAULT_CONFIG_PATH,
    working_dir: Annotated[
        Path | None, typer.Option("--working-dir", "-w", help="Override working directory")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print commands without executing")
    ] = False,
    extra_args: Annotated[
        str | None,
        typer.Option(
            "--extra-args", help="Extra terraform args from PR comment (e.g., --target=module.base)"
        ),
    ] = None,
) -> None:
    """
    Execute terraform for the specified environment.

    This mode does NOT call branch-deploy - it assumes you've already
    done that and are passing the environment/sha from those outputs.

    Dynamic args can be passed via PR comment:
      .plan to dev | --target=module.base --target=module.network
    """
    console.print(
        Panel.fit("[bold blue]Terraform Branch Deploy[/bold blue] v0.2.0", subtitle="Execute Mode")
    )

    config, env_config = _load_and_validate_config(config_path, environment)
    resolved_working_dir = Path(working_dir or env_config.working_directory)

    raw_extra_args = extra_args or os.environ.get("TF_BD_EXTRA_ARGS")
    parsed_extra_args = []

    if raw_extra_args:
        parsed_extra_args = _parse_extra_args(raw_extra_args)
        console.print(f"[cyan]📝 Extra args from command:[/cyan] {parsed_extra_args}")

    table = Table(title="Terraform Execution")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Environment", environment)
    table.add_row("Operation", operation)
    table.add_row("SHA", sha[:8])
    table.add_row("Working Dir", str(resolved_working_dir))
    table.add_row("Dry Run", str(dry_run))
    if parsed_extra_args:
        table.add_row("Extra Args", " ".join(parsed_extra_args))
    console.print(table)

    var_files = config.resolve_var_files(environment)
    backend_configs = config.resolve_backend_configs(environment)
    init_args = config.resolve_args(environment, "init_args")
    plan_args = config.resolve_args(environment, "plan_args") + parsed_extra_args
    apply_args = config.resolve_args(environment, "apply_args") + parsed_extra_args

    set_github_output("working_directory", str(resolved_working_dir))
    set_github_output("var_files", json.dumps(var_files))
    set_github_output("is_production", str(config.is_production(environment)).lower())

    if dry_run:
        console.print("\n[yellow]🧪 Dry run - commands would be:[/yellow]")
        console.print(f"  cd {resolved_working_dir}")
        console.print(f"  terraform init {' '.join(init_args)}")
        if operation == "plan":
            console.print(f"  terraform plan {' '.join(plan_args)}")
        else:
            console.print(f"  terraform apply {' '.join(apply_args)}")
        return

    from .executor import TerraformExecutor

    pr_number_str = os.environ.get("TF_BD_PR_NUMBER", "")
    try:
        pr_number = int(pr_number_str) if pr_number_str else None
    except ValueError:
        console.print(f"[yellow]⚠️ Invalid TF_BD_PR_NUMBER: {pr_number_str}, ignoring[/yellow]")
        pr_number = None

    executor = TerraformExecutor(
        working_directory=resolved_working_dir,
        var_files=var_files,
        backend_configs=backend_configs,
        init_args=init_args,
        plan_args=plan_args,
        apply_args=apply_args,
        github_token=os.environ.get("GITHUB_TOKEN"),
        repo=os.environ.get("GITHUB_REPOSITORY"),
        pr_number=pr_number,
    )

    init_result = executor.init()
    if not init_result.success:
        console.print("[red]Terraform init failed[/red]")
        set_github_output("failure_reason", "Terraform initialization failed. Check logs for details.")
        raise typer.Exit(1)

    if operation == "plan":
        _handle_plan(executor, environment, sha)
    elif operation == "apply" or operation == "rollback":
        _handle_apply(executor, environment, sha, resolved_working_dir)
    else:
        msg = f"Unknown operation: {operation}"
        console.print(f"[red]{msg}[/red]")
        set_github_output("failure_reason", msg)
        raise typer.Exit(1)

    console.print("\n[green]✅ Terraform execution complete[/green]")


def _handle_plan(executor: "TerraformExecutor", environment: str, sha: str) -> None:
    """Handle terraform plan operation."""

    plan_file = Path(f"tfplan-{environment}-{sha[:8]}.tfplan")
    result = executor.plan(out_file=plan_file)
    if result.plan_file and result.checksum:
        set_github_output("plan_file", str(result.plan_file))
        set_github_output("plan_checksum", result.checksum)
        set_github_output("has_changes", str(result.has_changes).lower())
    if not result.success:
        logs_url = (
            os.environ.get("GITHUB_SERVER_URL", GITHUB_URL_DEFAULT)
            + "/"
            + os.environ.get("GITHUB_REPOSITORY", "")
            + ACTIONS_RUNS_PATH
            + os.environ.get("GITHUB_RUN_ID", "")
        )
        error_msg = format_error_for_comment(
            message="Terraform plan failed. The `terraform plan` command exited with an error.",
            logs_url=logs_url,
            suggestion=f"Fix any configuration errors and run `.plan to {environment}` again",
        )
        set_github_output("failure_reason", error_msg)
        raise typer.Exit(1)


def _handle_apply(
    executor: "TerraformExecutor", environment: str, sha: str, working_dir: Path
) -> None:
    """Handle terraform apply operation."""
    plan_filename = f"tfplan-{environment}-{sha[:8]}.tfplan"
    plan_file = working_dir / plan_filename
    is_rollback = os.environ.get("TF_BD_IS_ROLLBACK", "false").lower() == "true"

    if plan_file.exists():
        _apply_with_plan(executor, plan_file)
        console.print(f"[dim]📋 Plan applied: {plan_filename}[/dim]")
    elif is_rollback:
        console.print(
            "[yellow]⚡ Rollback detected - applying directly from stable branch[/yellow]"
        )
        apply_result = executor.apply()
        if not apply_result.success:
            logs_url = (
                os.environ.get("GITHUB_SERVER_URL", GITHUB_URL_DEFAULT)
                + "/"
                + os.environ.get("GITHUB_REPOSITORY", "")
                + ACTIONS_RUNS_PATH
                + os.environ.get("GITHUB_RUN_ID", "")
            )
            error_msg = format_error_for_comment(
                message="Rollback apply failed. Terraform encountered an error applying the stable branch state.",
                logs_url=logs_url,
                suggestion="Ensure the `main` branch has valid Terraform configuration and remote state is accessible",
            )
            set_github_output("failure_reason", error_msg)
            raise typer.Exit(1)
        console.print("[dim]📋 Rollback applied directly (no plan file)[/dim]")
    else:
        console.print(f"[red]❌ No plan file found for this SHA: {plan_file}[/red]")
        error_msg = format_error_for_comment(
            message=f"No plan file found for this commit. You attempted to apply changes, but no saved plan exists for commit `{sha[:8]}`.",
            details=f"- Run `.plan to {environment}` to create a plan\n- For rollback to stable: `.apply main to {environment}`",
            suggestion=f"Run `.plan to {environment}` first, then `.apply to {environment}`",
        )
        set_github_output("failure_reason", error_msg)
        console.print(
            f"[yellow]💡 You must run '.plan to {environment}' before '.apply to {environment}'[/yellow]"
        )
        console.print(
            f"[yellow]💡 For rollback, use: '.apply main to {environment}' (from stable branch)[/yellow]"
        )
        raise typer.Exit(1)


def _apply_with_plan(executor: "TerraformExecutor", plan_file: Path) -> None:
    """Apply using an existing plan file with checksum verification."""
    console.print(f"[green]✅ Found plan file:[/green] {plan_file}")
    expected_checksum = os.environ.get("TF_BD_PLAN_CHECKSUM")

    if expected_checksum:
        from .artifacts import verify_checksum

        if not verify_checksum(plan_file, expected_checksum):
            console.print(
                "[red]❌ Plan file checksum mismatch! Plan may have been tampered with.[/red]"
            )
            env = os.environ.get('TF_BD_ENVIRONMENT', 'dev')
            error_msg = format_error_for_comment(
                message="Security validation failed: Plan file checksum mismatch. The plan file's checksum does not match the expected value, which could indicate tampering or corruption.",
                suggestion=f"Create a fresh plan by running `.plan to {env}`",
            )
            set_github_output("failure_reason", error_msg)
            raise typer.Exit(1)
        console.print("[green]✅ Plan checksum verified[/green]")

    apply_result = executor.apply(plan_file=Path(plan_file.name))
    if not apply_result.success:
        logs_url = (
            os.environ.get("GITHUB_SERVER_URL", GITHUB_URL_DEFAULT)
            + "/"
            + os.environ.get("GITHUB_REPOSITORY", "")
            + ACTIONS_RUNS_PATH
            + os.environ.get("GITHUB_RUN_ID", "")
        )
        env = os.environ.get('TF_BD_ENVIRONMENT', 'dev')
        error_msg = format_error_for_comment(
            message="Terraform apply failed. The `terraform apply` command exited with an error after applying the plan.",
            logs_url=logs_url,
            suggestion=f"Identify the root cause and create a new plan with `.plan to {env}`",
        )
        set_github_output("failure_reason", error_msg)
        raise typer.Exit(1)


@app.command()
def validate(
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to .tf-branch-deploy.yml")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Validate the configuration file."""
    console.print(f"🔍 Validating [cyan]{config_path}[/cyan]")

    try:
        config = load_config(config_path)
        console.print("[green]✅ Configuration is valid[/green]")

        table = Table(title="Configuration Summary")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Environments", ", ".join(config.environments.keys()))
        table.add_row("Default", config.default_environment)
        table.add_row("Production", ", ".join(config.production_environments))
        table.add_row("Stable Branch", config.stable_branch)
        console.print(table)

    except FileNotFoundError:
        console.print(f"[red]❌ Config file not found:[/red] {config_path}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]❌ Configuration error:[/red] {e}")
        raise typer.Exit(1) from None


@app.command()
def schema() -> None:
    """Output the JSON schema for .tf-branch-deploy.yml."""
    from .config import generate_json_schema

    schema_json = generate_json_schema()
    console.print_json(data=schema_json)


@app.command()
def environments(
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to .tf-branch-deploy.yml")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """List available environments (comma-separated for branch-deploy)."""
    try:
        config = load_config(config_path)
        env_list = ",".join(config.environments.keys())
        console.print(env_list)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] Failed to load config: {e}")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
