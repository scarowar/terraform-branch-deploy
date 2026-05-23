"""
Terraform Branch Deploy CLI.

Typer-based CLI for Terraform infrastructure deployments via GitHub PRs.

Two modes:
- trigger: [For action.yml] Parse command, export TF_BD_* env vars, STOP
- execute: [For action.yml] Run terraform with lifecycle completion
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
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
from .executor import _redact_single_arg

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
        delimiter = f"TFBD_{name}_{uuid.uuid4().hex}"
        while delimiter in value:
            delimiter = f"TFBD_{name}_{uuid.uuid4().hex}"

        with open(output_file, "a", encoding="utf-8") as f:
            f.write(f"{name}<<{delimiter}\n{value}\n{delimiter}\n")

    preview = value.replace("\r", "\\r").replace("\n", "\\n")
    console.print(f"[dim]Output: {name}={preview[:50]}{'...' if len(preview) > 50 else ''}[/dim]")


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


ALLOWED_EXTRA_ARG_FLAGS: frozenset[str] = frozenset(
    {
        "-target",
        "-var",
        "-var-file",
        "-refresh",
        "-parallelism",
        "-compact-warnings",
        "-lock",
        "-lock-timeout",
        "-replace",
    }
)

ALLOWED_APPLY_CONFIG_ARG_FLAGS: frozenset[str] = frozenset(
    {
        "-var",
        "-var-file",
        "-parallelism",
        "-compact-warnings",
        "-lock",
        "-lock-timeout",
    }
)

ARG_FLAGS_WITH_SEPARATE_VALUES: frozenset[str] = frozenset(
    {
        "-target",
        "-var",
        "-var-file",
        "-parallelism",
        "-lock-timeout",
        "-replace",
    }
)

ARG_FLAGS_WITH_OPTIONAL_SEPARATE_VALUES: frozenset[str] = frozenset(
    {
        "-lock",
        "-refresh",
    }
)


BLOCKED_EXTRA_ARG_FLAGS: frozenset[str] = frozenset(
    {
        "-destroy",
        "-backend-config",
        "-migrate-state",
        "-state",
        "-force-unlock",
        "-reconfigure",
    }
)

VALID_OPERATIONS: frozenset[str] = frozenset({"plan", "apply", "rollback"})

NON_PLAN_EXTRA_ARGS_ERROR = (
    "Extra Terraform arguments are only supported on plan commands. "
    "Apply uses the saved plan. Rollback applies the stable branch directly; "
    "Terraform does not provide a deterministic target-only rollback."
)


def _redact_args_for_display(args: list[str]) -> list[str]:
    """Redact argument values before showing PR-supplied or metadata args."""
    return [_redact_single_arg(arg) for arg in args]


def _validate_args_allowed(
    args: list[str],
    allowed_flags: frozenset[str],
    source: str,
) -> list[str]:
    """Validate args against an allowlist for a specific source."""
    validated: list[str] = []
    i = 0

    while i < len(args):
        arg = args[i]
        if not arg.startswith("-"):
            console.print(f"[red]❌ Unsupported {source} arg value without flag: {arg}[/red]")
            raise typer.Exit(1)

        flag = arg.split("=", 1)[0] if "=" in arg else arg

        if flag in BLOCKED_EXTRA_ARG_FLAGS or flag not in allowed_flags:
            console.print(f"[red]❌ Unsupported {source} arg: {flag}[/red]")
            console.print(f"[red]Allowed {source} flags: {', '.join(sorted(allowed_flags))}[/red]")
            raise typer.Exit(1)

        validated.append(arg)

        if "=" not in arg and flag in ARG_FLAGS_WITH_SEPARATE_VALUES:
            if i + 1 >= len(args) or args[i + 1].startswith("-"):
                console.print(f"[red]❌ Missing value for {source} arg: {flag}[/red]")
                raise typer.Exit(1)
            validated.append(args[i + 1])
            i += 1
        elif "=" not in arg and flag in ARG_FLAGS_WITH_OPTIONAL_SEPARATE_VALUES:
            if i + 1 < len(args) and not args[i + 1].startswith("-"):
                validated.append(args[i + 1])
                i += 1

        i += 1

    return validated


def _validate_extra_args(args: list[str]) -> list[str]:
    """Validate parsed extra args against the allowlist.

    Raises:
        typer.Exit: If any arg uses a blocked or unknown flag.
    """
    return _validate_args_allowed(args, ALLOWED_EXTRA_ARG_FLAGS, "PR comment")


def _validate_config_args(
    plan_args: list[str],
    apply_args: list[str],
) -> None:
    """Validate configured Terraform args before any Terraform command runs."""
    _validate_args_allowed(plan_args, ALLOWED_EXTRA_ARG_FLAGS, "plan-args")
    _validate_args_allowed(apply_args, ALLOWED_APPLY_CONFIG_ARG_FLAGS, "apply-args")


def _resolve_extra_plan_args(operation: str, raw_extra_args: str | None) -> list[str]:
    """Parse and validate PR comment args for plan operations."""
    if operation != "plan" and raw_extra_args and raw_extra_args.strip():
        msg = NON_PLAN_EXTRA_ARGS_ERROR
        console.print(f"[red]❌ {msg}[/red]")
        set_github_output("failure_reason", msg)
        raise typer.Exit(1)

    if not raw_extra_args:
        return []

    parsed_args = _validate_extra_args(_parse_extra_args(raw_extra_args))
    console.print(
        f"[cyan]📝 Extra args from command:[/cyan] {_redact_args_for_display(parsed_args)}"
    )
    return parsed_args


def _print_execution_table(
    environment: str,
    operation: str,
    sha: str,
    working_dir: Path,
    dry_run: bool,
    parsed_extra_args: list[str],
) -> None:
    """Display execution context without exposing sensitive variable values."""
    table = Table(title="Terraform Execution")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Environment", environment)
    table.add_row("Operation", operation)
    table.add_row("SHA", sha[:8])
    table.add_row("Working Dir", str(working_dir))
    table.add_row("Dry Run", str(dry_run))
    if parsed_extra_args:
        table.add_row(
            "Extra Args",
            " ".join(_redact_single_arg(arg) for arg in parsed_extra_args),
        )
    console.print(table)


def _print_dry_run_commands(
    working_dir: Path,
    operation: str,
    init_args: list[str],
    var_files: list[str],
    plan_args: list[str],
    apply_args: list[str],
) -> None:
    """Print the Terraform commands that would run in dry-run mode."""
    console.print("\n[yellow]🧪 Dry run - commands would be:[/yellow]")
    console.print(f"  cd {working_dir}")
    console.print(f"  terraform init {' '.join(init_args)}")
    if operation == "plan":
        console.print(f"  terraform plan {' '.join(plan_args)}")
    elif operation == "apply":
        console.print("  terraform apply <saved plan file>")
    else:
        rollback_args: list[str] = []
        for var_file in var_files:
            rollback_args.extend(["-var-file", var_file])
        rollback_args.extend(apply_args)
        console.print(f"  terraform apply {' '.join(rollback_args)}")


def _pr_number_from_env() -> int | None:
    """Parse TF_BD_PR_NUMBER for tfcmt comments."""
    pr_number_str = os.environ.get("TF_BD_PR_NUMBER", "")
    if not pr_number_str:
        return None
    try:
        return int(pr_number_str)
    except ValueError:
        console.print(f"[yellow]⚠️ Invalid TF_BD_PR_NUMBER: {pr_number_str}, ignoring[/yellow]")
        return None


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
    key: Annotated[
        str,
        typer.Argument(
            help="Config key to retrieve (default-environment or production-environments)"
        ),
    ],
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
    failure_reason: Annotated[
        str | None, typer.Option(help="Reason for failure if status is failure")
    ] = None,
) -> None:
    """Complete the deployment lifecycle (update status, reactions, comments)."""
    from .lifecycle import LifecycleManager

    # Gather context from env vars
    env_vars = dict(os.environ)
    repo = env_vars.get("GH_REPO") or env_vars.get("GITHUB_REPOSITORY")
    token = env_vars.get("GITHUB_TOKEN")

    if not repo or not token:
        console.print("[red]Error:[/red] GH_REPO/GITHUB_REPOSITORY or GITHUB_TOKEN not set")
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
    operation: Annotated[str, typer.Option("--operation", "-o", help="plan, apply, or rollback")],
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
      .plan to dev | -target=module.base -target=module.network
    """
    console.print(
        Panel.fit("[bold blue]Terraform Branch Deploy[/bold blue] v0.2.0", subtitle="Execute Mode")
    )

    config, env_config = _load_and_validate_config(config_path, environment)
    resolved_working_dir = Path(working_dir or env_config.working_directory)

    if operation not in VALID_OPERATIONS:
        msg = f"Unknown operation: {operation}"
        console.print(f"[red]{msg}[/red]")
        set_github_output("failure_reason", msg)
        raise typer.Exit(1)

    raw_extra_args = extra_args or os.environ.get("TF_BD_EXTRA_ARGS")
    parsed_extra_args = _resolve_extra_plan_args(operation, raw_extra_args)
    _print_execution_table(
        environment, operation, sha, resolved_working_dir, dry_run, parsed_extra_args
    )

    var_files = config.resolve_var_files(environment)
    backend_configs = config.resolve_backend_configs(environment)
    init_args = config.resolve_args(environment, "init_args")
    config_plan_args = config.resolve_args(environment, "plan_args")
    apply_args = config.resolve_args(environment, "apply_args")
    _validate_config_args(config_plan_args, apply_args)
    plan_args = config_plan_args + parsed_extra_args

    set_github_output("working_directory", str(resolved_working_dir))
    set_github_output("var_files", json.dumps(var_files))
    set_github_output("is_production", str(config.is_production(environment)).lower())

    if dry_run:
        _print_dry_run_commands(
            resolved_working_dir, operation, init_args, var_files, plan_args, apply_args
        )
        return

    from .executor import TerraformExecutor

    executor = TerraformExecutor(
        working_directory=resolved_working_dir,
        var_files=var_files,
        backend_configs=backend_configs,
        init_args=init_args,
        plan_args=plan_args,
        apply_args=apply_args,
        github_token=os.environ.get("GITHUB_TOKEN"),
        repo=os.environ.get("GITHUB_REPOSITORY"),
        pr_number=_pr_number_from_env(),
        timeout=env_config.timeout,
    )

    init_result = executor.init()
    if not init_result.success:
        console.print("[red]Terraform init failed[/red]")
        set_github_output(
            "failure_reason", "Terraform initialization failed. Check logs for details."
        )
        raise typer.Exit(1)

    if operation == "plan":
        _handle_plan(executor, environment, sha, plan_args, var_files)
    else:
        _handle_apply(
            executor,
            environment,
            sha,
            resolved_working_dir,
            is_rollback=operation == "rollback",
        )

    console.print("\n[green]✅ Terraform execution complete[/green]")


def _handle_plan(
    executor: "TerraformExecutor",
    environment: str,
    sha: str,
    plan_args: list[str],
    var_files: list[str],
) -> None:
    """Handle terraform plan operation."""

    plan_file = Path(f"tfplan-{environment}-{sha[:8]}.tfplan")
    result = executor.plan(out_file=plan_file)
    if result.plan_file and result.checksum:
        set_github_output("plan_file", str(result.plan_file))
        set_github_output("plan_checksum", result.checksum)
        set_github_output("has_changes", str(result.has_changes).lower())

        # Save plan metadata sidecar for cross-run integrity verification
        from .artifacts import PlanMetadata, generate_params_hash, save_plan_metadata

        extra_args_str = os.environ.get("TF_BD_EXTRA_ARGS", "")
        tf_version = executor.version()
        params_hash = generate_params_hash(extra_args_str)

        metadata = PlanMetadata(
            environment=environment,
            sha=sha,
            checksum=result.checksum,
            extra_args=_parse_extra_args(extra_args_str) if extra_args_str.strip() else [],
            plan_args=plan_args,
            var_files=var_files,
            terraform_version=tf_version,
            params_hash=params_hash,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        meta_path = save_plan_metadata(result.plan_file, metadata)
        console.print(f"[dim]📝 Plan metadata saved: {meta_path.name}[/dim]")

        set_github_output("plan_params_hash", params_hash)
        set_github_output("plan_terraform_version", tf_version)

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
    executor: "TerraformExecutor",
    environment: str,
    sha: str,
    working_dir: Path,
    is_rollback: bool | None = None,
) -> None:
    """Handle terraform apply operation."""
    plan_filename = f"tfplan-{environment}-{sha[:8]}.tfplan"
    plan_file = working_dir / plan_filename
    if is_rollback is None:
        is_rollback = os.environ.get("TF_BD_IS_ROLLBACK", "false").lower() == "true"
    raw_extra_args = os.environ.get("TF_BD_EXTRA_ARGS", "")

    if raw_extra_args.strip():
        msg = NON_PLAN_EXTRA_ARGS_ERROR
        console.print(f"[red]❌ {msg}[/red]")
        set_github_output("failure_reason", msg)
        raise typer.Exit(1)

    if is_rollback:
        console.print(
            "[yellow]⚡ Rollback detected - applying directly from stable branch[/yellow]"
        )
        console.print(
            "[yellow]⚠️  WARNING: Rollback applies the full stable-branch state without a reviewed plan. "
            "Ensure the stable branch configuration is correct before proceeding.[/yellow]"
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
    elif plan_file.exists():
        _apply_with_plan(executor, plan_file, environment, sha)
        console.print(f"[dim]📋 Plan applied: {plan_filename}[/dim]")
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


def _apply_with_plan(
    executor: "TerraformExecutor",
    plan_file: Path,
    environment: str,
    sha: str,
) -> None:
    """Apply using an existing plan file with integrity verification.

    Metadata sidecar (.meta.json) is mandatory for v0.2.0.
    """
    console.print(f"[green]✅ Found plan file:[/green] {plan_file}")

    from .artifacts import load_plan_metadata, verify_checksum

    metadata = load_plan_metadata(plan_file)

    if metadata is None:
        error_msg = format_error_for_comment(
            message=(
                "Saved plan metadata was not found or could not be read. "
                "Terraform Branch Deploy refuses to apply an unverified saved plan."
            ),
            suggestion=f"Create a fresh plan by running `.plan to {environment}`",
        )
        set_github_output("failure_reason", error_msg)
        raise typer.Exit(1)

    if metadata.environment != environment:
        error_msg = format_error_for_comment(
            message=(
                f"Saved plan environment mismatch: plan was created for "
                f"`{metadata.environment}`, but apply requested `{environment}`."
            ),
            suggestion=f"Create a fresh plan by running `.plan to {environment}`",
        )
        set_github_output("failure_reason", error_msg)
        raise typer.Exit(1)

    if metadata.sha != sha:
        error_msg = format_error_for_comment(
            message=(
                f"Saved plan commit mismatch: plan was created for `{metadata.sha[:8]}`, "
                f"but apply requested `{sha[:8]}`."
            ),
            suggestion=f"Create a fresh plan by running `.plan to {environment}`",
        )
        set_github_output("failure_reason", error_msg)
        raise typer.Exit(1)

    if not verify_checksum(plan_file, metadata.checksum):
        console.print(
            "[red]❌ Plan file checksum mismatch! "
            "Plan may have been tampered with or corrupted.[/red]"
        )
        error_msg = format_error_for_comment(
            message=(
                "Security validation failed: Plan file checksum mismatch. "
                "The plan file's integrity could not be verified against "
                "the metadata recorded at plan time."
            ),
            suggestion=f"Create a fresh plan by running `.plan to {environment}`",
        )
        set_github_output("failure_reason", error_msg)
        raise typer.Exit(1)
    console.print("[green]✅ Plan checksum verified[/green]")

    current_tf_version = executor.version()
    if (
        current_tf_version != "unknown"
        and metadata.terraform_version != "unknown"
        and current_tf_version != metadata.terraform_version
    ):
        console.print(
            f"[red]❌ Terraform version mismatch![/red]\n"
            f"    Plan created with: {metadata.terraform_version}\n"
            f"    Current version:   {current_tf_version}"
        )
        error_msg = format_error_for_comment(
            message=(
                f"Terraform version mismatch: plan was created with "
                f"v{metadata.terraform_version} but current version is "
                f"v{current_tf_version}. Applying a plan with a different "
                f"Terraform version can cause unpredictable behavior."
            ),
            suggestion=f"Create a fresh plan with `.plan to {environment}` using the current Terraform version",
        )
        set_github_output("failure_reason", error_msg)
        raise typer.Exit(1)
    if current_tf_version != "unknown":
        console.print(f"[green]✅ Terraform version verified: {current_tf_version}[/green]")

    if metadata.extra_args:
        console.print(
            "[dim]📝 Plan was created with args: "
            f"{' '.join(_redact_args_for_display(metadata.extra_args))}[/dim]"
        )
    console.print(f"[dim]📝 Plan created at: {metadata.created_at}[/dim]")

    # Pass only the filename to the executor — not the full path.
    # The executor resolves plan_file relative to its working_directory,
    # so passing the full path (which already includes working_directory)
    # would cause path doubling: working_dir/working_dir/filename.
    apply_result = executor.apply(plan_file=Path(plan_file.name))
    if not apply_result.success:
        logs_url = (
            os.environ.get("GITHUB_SERVER_URL", GITHUB_URL_DEFAULT)
            + "/"
            + os.environ.get("GITHUB_REPOSITORY", "")
            + ACTIONS_RUNS_PATH
            + os.environ.get("GITHUB_RUN_ID", "")
        )
        env = os.environ.get("TF_BD_ENVIRONMENT", "dev")
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
