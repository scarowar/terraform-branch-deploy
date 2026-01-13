"""
Terraform Branch Deploy CLI.

Typer-based CLI for Terraform infrastructure deployments via GitHub PRs.

Three modes:
- parse: Just read config, no branch-deploy, no terraform
- dispatch: [For action.yml] Full flow with branch-deploy
- execute: Just run terraform, no branch-deploy
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from .executor import TerraformExecutor

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_config

# Constants
DEFAULT_CONFIG_PATH = Path(".tf-branch-deploy.yml")

app = typer.Typer(
    name="tf-branch-deploy",
    help="ChatOps for Terraform infrastructure deployments via GitHub PRs.",
    no_args_is_help=True,
)
console = Console()


class Mode(str, Enum):
    """Execution mode."""

    PARSE = "parse"  # Just read config, output settings
    DISPATCH = "dispatch"  # Full flow (called by action.yml internally)
    EXECUTE = "execute"  # Just run terraform


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
    # Find the first = to split flag from value
    eq_pos = arg.find("=")
    if eq_pos == -1:
        return arg  # No value part (e.g., just a flag)

    flag = arg[: eq_pos + 1]  # e.g., "-var="
    value = arg[eq_pos + 1 :]  # e.g., "'key=value'"

    # Strip outer quotes from value if present
    if len(value) >= 2:
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]

    return flag + value


@app.command()
def parse(
    environment: Annotated[str, typer.Option("--environment", "-e", help="Target environment")],
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to .tf-branch-deploy.yml")
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """
    Parse config and output settings for an environment.

    This mode does NOT call branch-deploy or run terraform.
    Use this when you need config info before calling branch-deploy yourself.
    """
    console.print(
        Panel.fit("[bold blue]Terraform Branch Deploy[/bold blue] v0.2.0", subtitle="Parse Mode")
    )

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

    env_config = config.get_environment(environment)

    # Resolve all settings
    var_files = config.resolve_var_files(environment)
    backend_configs = config.resolve_backend_configs(environment)
    init_args = config.resolve_args(environment, "init_args")
    plan_args = config.resolve_args(environment, "plan_args")
    apply_args = config.resolve_args(environment, "apply_args")

    # Set outputs
    set_github_output("working_directory", env_config.working_directory)
    set_github_output("var_files", json.dumps(var_files))
    set_github_output("backend_configs", json.dumps(backend_configs))
    set_github_output("init_args", json.dumps(init_args))
    set_github_output("plan_args", json.dumps(plan_args))
    set_github_output("apply_args", json.dumps(apply_args))
    set_github_output("is_production", str(config.is_production(environment)).lower())

    console.print(f"[green]✅ Parsed config for environment: {environment}[/green]")


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

    env_config = config.get_environment(environment)
    resolved_working_dir = Path(working_dir or env_config.working_directory)

    # Parse extra args - check env var first (set by action.yml), then CLI option
    # Using env var avoids shell escaping issues with complex args like -var='key=value'
    import os

    raw_extra_args = extra_args or os.environ.get("TF_BD_EXTRA_ARGS")
    parsed_extra_args = []

    if raw_extra_args:
        # Custom parser that splits on unquoted spaces but preserves quotes in values
        # This handles -target=module.test["key"] and -var='key=value' correctly
        parsed_extra_args = _parse_extra_args(raw_extra_args)
        console.print(f"[cyan]📝 Extra args from command:[/cyan] {parsed_extra_args}")

    # Display info
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

    # Resolve args from config
    var_files = config.resolve_var_files(environment)
    backend_configs = config.resolve_backend_configs(environment)
    init_args = config.resolve_args(environment, "init_args")
    plan_args = config.resolve_args(environment, "plan_args") + parsed_extra_args
    apply_args = config.resolve_args(environment, "apply_args") + parsed_extra_args

    # Set outputs for any downstream steps
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

    # Actually execute terraform
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
        pr_number=int(os.environ.get("TF_BD_PR_NUMBER", "0")) or None,
    )

    # Init
    init_result = executor.init()
    if not init_result.success:
        console.print("[red]Terraform init failed[/red]")
        raise typer.Exit(1)

    # Plan or Apply
    if operation == "plan":
        _handle_plan(executor, environment, sha)
    elif operation == "apply":
        _handle_apply(executor, environment, sha, resolved_working_dir)
    else:
        console.print(f"[red]Unknown operation: {operation}[/red]")
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
        raise typer.Exit(1)


def _handle_apply(
    executor: "TerraformExecutor", environment: str, sha: str, working_dir: Path
) -> None:
    """Handle terraform apply operation."""
    plan_filename = f"tfplan-{environment}-{sha[:8]}.tfplan"
    plan_file = working_dir / plan_filename
    is_rollback = os.environ.get("TF_BD_IS_ROLLBACK", "false").lower() == "true"

    if plan_file.exists():
        _apply_with_plan(executor, plan_file, plan_filename)
    elif is_rollback:
        console.print(
            "[yellow]⚡ Rollback detected - applying directly from stable branch[/yellow]"
        )
        apply_result = executor.apply()
        if not apply_result.success:
            raise typer.Exit(1)
    else:
        console.print(f"[red]❌ No plan file found for this SHA: {plan_file}[/red]")
        console.print("[yellow]💡 You must run '.plan to {env}' before '.apply to {env}'[/yellow]")
        console.print(
            "[yellow]💡 For rollback, use: '.apply main to {env}' (from stable branch)[/yellow]"
        )
        raise typer.Exit(1)

    console.print(f"[dim]📋 Plan applied: {plan_filename}[/dim]")


def _apply_with_plan(executor: "TerraformExecutor", plan_file: Path, plan_filename: str) -> None:
    """Apply using an existing plan file with checksum verification."""
    console.print(f"[green]✅ Found plan file:[/green] {plan_file}")
    expected_checksum = os.environ.get("TF_BD_PLAN_CHECKSUM")

    if expected_checksum:
        from .artifacts import verify_checksum

        if not verify_checksum(plan_file, expected_checksum):
            console.print(
                "[red]❌ Plan file checksum mismatch! Plan may have been tampered with.[/red]"
            )
            raise typer.Exit(1)
        console.print("[green]✅ Plan checksum verified[/green]")

    apply_result = executor.apply(plan_file=Path(plan_filename))
    if not apply_result.success:
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
    except Exception:
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
