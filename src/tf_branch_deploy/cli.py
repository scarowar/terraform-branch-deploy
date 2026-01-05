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

    PARSE = "parse"      # Just read config, output settings
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


@app.command()
def parse(
    environment: Annotated[str, typer.Option("--environment", "-e", help="Target environment")],
    config_path: Annotated[
        Path, typer.Option("--config", "-c", help="Path to .tf-branch-deploy.yml")
    ] = Path(".tf-branch-deploy.yml"),
) -> None:
    """
    Parse config and output settings for an environment.

    This mode does NOT call branch-deploy or run terraform.
    Use this when you need config info before calling branch-deploy yourself.
    """
    console.print(Panel.fit(
        "[bold blue]Terraform Branch Deploy[/bold blue] v0.2.0",
        subtitle="Parse Mode"
    ))

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
    ] = Path(".tf-branch-deploy.yml"),
    working_dir: Annotated[
        Path | None, typer.Option("--working-dir", "-w", help="Override working directory")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print commands without executing")
    ] = False,
    extra_args: Annotated[
        str | None, typer.Option("--extra-args", help="Extra terraform args from PR comment (e.g., --target=module.base)")
    ] = None,
) -> None:
    """
    Execute terraform for the specified environment.

    This mode does NOT call branch-deploy - it assumes you've already
    done that and are passing the environment/sha from those outputs.

    Dynamic args can be passed via PR comment:
      .plan to dev | --target=module.base --target=module.network
    """
    console.print(Panel.fit(
        "[bold blue]Terraform Branch Deploy[/bold blue] v0.2.0",
        subtitle="Execute Mode"
    ))

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

    # Parse extra args (e.g., "--target=module.base --target=module.network")
    parsed_extra_args = []
    if extra_args:
        # Split respecting quotes and equals signs
        import shlex
        try:
            parsed_extra_args = shlex.split(extra_args)
        except ValueError:
            parsed_extra_args = extra_args.split()
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
        # Plan file should be just the filename - executor runs from working_directory
        plan_file = Path(f"tfplan-{environment}-{sha[:8]}.tfplan")
        result = executor.plan(out_file=plan_file)
        if result.plan_file and result.checksum:
            set_github_output("plan_file", str(result.plan_file))
            set_github_output("plan_checksum", result.checksum)
            set_github_output("has_changes", str(result.has_changes).lower())
        if not result.success:
            raise typer.Exit(1)
    elif operation == "apply":
        # Look for the plan file from a previous .plan command
        # Plan file is in the working directory, not repo root
        plan_filename = f"tfplan-{environment}-{sha[:8]}.tfplan"
        plan_file = resolved_working_dir / plan_filename
        
        # Check if this is a rollback (ref output from branch-deploy)
        # Rollback syntax: .apply main to dev (stable_branch → environment)
        is_rollback = os.environ.get("TF_BD_IS_ROLLBACK", "false").lower() == "true"
        
        if plan_file.exists():
            console.print(f"[green]✅ Found plan file:[/green] {plan_file}")
            # Verify checksum if we have one stored
            expected_checksum = os.environ.get("TF_BD_PLAN_CHECKSUM")
            if expected_checksum:
                from .artifacts import verify_checksum
                if not verify_checksum(plan_file, expected_checksum):
                    console.print("[red]❌ Plan file checksum mismatch! Plan may have been tampered with.[/red]")
                    raise typer.Exit(1)
                console.print("[green]✅ Plan checksum verified[/green]")
            # Pass just the filename since executor runs from working_directory
            result = executor.apply(plan_file=Path(plan_filename))
        elif is_rollback:
            console.print("[yellow]⚡ Rollback detected - applying directly from stable branch[/yellow]")
            result = executor.apply()
        else:
            console.print(f"[red]❌ No plan file found for this SHA: {plan_file}[/red]")
            console.print("[yellow]💡 You must run '.plan to {env}' before '.apply to {env}'[/yellow]")
            console.print("[yellow]💡 For rollback, use: '.apply main to {env}' (from stable branch)[/yellow]")
            raise typer.Exit(1)
        
        if not result.success:
            raise typer.Exit(1)
        
        # Delete plan file after successful apply to prevent re-use
        if plan_file.exists():
            plan_file.unlink()
            console.print(f"[dim]🗑️ Plan file consumed: {plan_filename}[/dim]")
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


# Keep backward compatibility with old 'run' command
@app.command(hidden=True)
def run(
    environment: Annotated[str, typer.Option("--environment", "-e")],
    operation: Annotated[str, typer.Option("--operation", "-o")],
    sha: Annotated[str, typer.Option("--sha", "-s")],
    config_path: Annotated[Path, typer.Option("--config", "-c")] = Path(".tf-branch-deploy.yml"),
    mode: Annotated[str, typer.Option("--mode", "-m")] = "execute",
    working_dir: Annotated[Path | None, typer.Option("--working-dir", "-w")] = None,
) -> None:
    """[DEPRECATED] Use 'parse' or 'execute' instead."""
    console.print("[yellow]⚠️ 'run' command is deprecated. Use 'parse' or 'execute'.[/yellow]")

    if mode == "skip":
        # Old skip mode = new parse mode
        parse(environment=environment, config_path=config_path)
    else:
        # Old run mode = new execute mode
        execute(
            environment=environment,
            operation=operation,
            sha=sha,
            config_path=config_path,
            working_dir=working_dir,
        )


if __name__ == "__main__":
    app()
