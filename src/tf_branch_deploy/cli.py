"""
Terraform Branch Deploy CLI.

Typer-based CLI for Terraform infrastructure deployments via GitHub PRs.
Supports two modes:
- skip: Just output config, don't run terraform
- run: Execute terraform (default)
"""

from __future__ import annotations

import json
import os
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config import load_config

app = typer.Typer(
    name="tf-branch-deploy",
    help="ChatOps for Terraform infrastructure deployments via GitHub PRs.",
    no_args_is_help=True,
)
console = Console()


class Mode(str, Enum):
    """Execution mode."""

    SKIP = "skip"
    RUN = "run"


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
    # Also print for debugging
    console.print(f"[dim]Output: {name}={value[:50]}{'...' if len(value) > 50 else ''}[/dim]")


@app.command()
def run(
    environment: Annotated[str, typer.Option("--environment", "-e", help="Target environment")],
    operation: Annotated[str, typer.Option("--operation", "-o", help="plan or apply")],
    sha: Annotated[str, typer.Option("--sha", "-s", help="Git commit SHA")],
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to .tf-branch-deploy.yml")
    ] = Path(".tf-branch-deploy.yml"),
    mode: Annotated[
        Mode, typer.Option("--mode", "-m", help="skip = outputs only, run = execute terraform")
    ] = Mode.RUN,
    working_dir: Annotated[
        Path | None, typer.Option("--working-dir", "-w", help="Override working directory")
    ] = None,
) -> None:
    """
    Execute Terraform operation for the specified environment.

    With mode=run (default): Actually executes terraform init/plan/apply
    With mode=skip: Just outputs config for use in subsequent steps
    """
    console.print(Panel.fit(
        "[bold blue]Terraform Branch Deploy[/bold blue] v0.2.0",
        subtitle="ChatOps for Terraform"
    ))

    # Load configuration
    console.print(f"\n📋 Loading config from [cyan]{config_path}[/cyan]")

    try:
        config = load_config(config_path)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Config file not found: {config_path}")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error:[/red] Invalid config: {e}")
        raise typer.Exit(1) from None

    # Validate environment exists
    if environment not in config.environments:
        console.print(f"[red]Error:[/red] Environment '{environment}' not found")
        console.print(f"Available: {list(config.environments.keys())}")
        raise typer.Exit(1)

    env_config = config.get_environment(environment)
    resolved_working_dir = Path(working_dir or env_config.working_directory)

    # Display environment info
    table = Table(title="Environment Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Environment", environment)
    table.add_row("Operation", operation)
    table.add_row("Mode", mode.value)
    table.add_row("SHA", sha[:8])
    table.add_row("Working Dir", str(resolved_working_dir))
    table.add_row("Is Production", str(config.is_production(environment)))

    console.print(table)

    # Resolve Terraform arguments
    var_files = config.resolve_var_files(environment)
    backend_configs = config.resolve_backend_configs(environment)
    init_args = config.resolve_args(environment, "init_args")
    plan_args = config.resolve_args(environment, "plan_args")
    apply_args = config.resolve_args(environment, "apply_args")

    # Set outputs for subsequent workflow steps
    set_github_output("working_directory", str(resolved_working_dir))
    set_github_output("var_files", json.dumps(var_files))
    set_github_output("backend_configs", json.dumps(backend_configs))
    set_github_output("init_args", json.dumps(init_args))
    set_github_output("plan_args", json.dumps(plan_args))
    set_github_output("apply_args", json.dumps(apply_args))
    set_github_output("is_production", str(config.is_production(environment)).lower())

    # If skip mode, we're done
    if mode == Mode.SKIP:
        console.print("\n[yellow]⏭️  Skip mode - outputs set, terraform not executed[/yellow]")
        return

    # === RUN MODE: Actually execute terraform ===
    console.print("\n[bold]🚀 Executing Terraform[/bold]")

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

    # Run init
    init_result = executor.init()
    if not init_result.success:
        console.print("[red]Terraform init failed[/red]")
        raise typer.Exit(1)

    # Run plan or apply
    if operation == "plan":
        plan_file = resolved_working_dir / f"tfplan-{environment}-{sha[:8]}.tfplan"
        result = executor.plan(out_file=plan_file)

        if result.plan_file and result.checksum:
            set_github_output("plan_file", str(result.plan_file))
            set_github_output("plan_checksum", result.checksum)
            set_github_output("has_changes", str(result.has_changes).lower())

        if not result.success:
            raise typer.Exit(1)

    elif operation == "apply":
        result = executor.apply()
        if not result.success:
            raise typer.Exit(1)

    else:
        console.print(f"[red]Unknown operation: {operation}[/red]")
        raise typer.Exit(1)

    console.print("\n[green]✅ Terraform execution complete[/green]")


@app.command()
def validate(
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to .tf-branch-deploy.yml")
    ] = Path(".tf-branch-deploy.yml"),
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
    ] = Path(".tf-branch-deploy.yml"),
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
