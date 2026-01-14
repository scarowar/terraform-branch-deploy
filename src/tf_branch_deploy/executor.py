"""
Terraform executor module.

Handles terraform init, plan, and apply operations with proper
argument resolution and PR comment posting via tfcmt.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 - subprocess is required to run terraform
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

# Constants
TF_INPUT_FALSE = "-input=false"

console = Console()


@dataclass
class CommandResult:
    """Result of a command execution."""

    exit_code: int
    stdout: str
    stderr: str
    command: list[str]

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class PlanResult(CommandResult):
    """Result of terraform plan."""

    has_changes: bool = False
    plan_file: Path | None = None
    checksum: str | None = None


@dataclass
class ApplyResult(CommandResult):
    """Result of terraform apply."""

    pass


@dataclass
class TerraformExecutor:
    """
    Executes Terraform operations.

    This is the core of tf-branch-deploy - we don't just configure,
    we actually RUN terraform.
    """

    working_directory: Path
    var_files: list[str] = field(default_factory=list)
    backend_configs: list[str] = field(default_factory=list)
    init_args: list[str] = field(default_factory=list)
    plan_args: list[str] = field(default_factory=list)
    apply_args: list[str] = field(default_factory=list)

    # GitHub context for comments
    github_token: str | None = None
    repo: str | None = None
    pr_number: int | None = None

    # tfcmt integration
    use_tfcmt: bool = True

    # Dry run mode - used by test fixtures to mark executor as non-production
    # Note: actual dry-run logic is in cli.py before executor is invoked
    dry_run: bool = False

    def _run_command(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Run a command and capture output."""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        console.print(f"[dim]$ {' '.join(args)}[/dim]")

        result = subprocess.run(  # nosec B603 B607 - args from validated config, terraform via PATH is expected
            args,
            cwd=self.working_directory,
            capture_output=True,
            text=True,
            env=full_env,
        )

        return CommandResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            command=args,
        )

    def init(self) -> CommandResult:
        """Run terraform init."""
        console.print("\n[bold blue]📦 Terraform Init[/bold blue]")

        args = ["terraform", "init", TF_INPUT_FALSE]

        # Add backend configs
        for backend in self.backend_configs:
            args.extend(["-backend-config", backend])

        # Add custom init args
        args.extend(self.init_args)

        result = self._run_command(args)

        if result.success:
            console.print("[green]✅ Init successful[/green]")
        else:
            console.print("[red]❌ Init failed[/red]")
            console.print(result.stderr)

        return result

    def plan(self, out_file: Path | None = None) -> PlanResult:
        """
        Run terraform plan.

        Args:
            out_file: Where to save the plan binary. If None, generates one.

        Returns:
            PlanResult with exit code, output, and plan file path.
        """
        console.print("\n[bold blue]📋 Terraform Plan[/bold blue]")

        if out_file is None:
            out_file = self.working_directory / "tfplan.bin"

        args = ["terraform", "plan", TF_INPUT_FALSE, "-detailed-exitcode"]

        # Add var files
        for var_file in self.var_files:
            args.extend(["-var-file", var_file])

        # Add output file
        args.extend(["-out", str(out_file)])

        # Add custom plan args
        args.extend(self.plan_args)

        # Use tfcmt if available
        if self.use_tfcmt and self._tfcmt_available():
            result = self._run_with_tfcmt("plan", args)
        else:
            result = self._run_command(args)

        # Terraform plan exit codes:
        # 0 = Success, no changes
        # 1 = Error
        # 2 = Success, changes present
        has_changes = result.exit_code == 2
        success = result.exit_code in (0, 2)

        if success:
            status = "with changes" if has_changes else "no changes"
            console.print(f"[green]✅ Plan successful ({status})[/green]")
        else:
            console.print("[red]❌ Plan failed[/red]")
            console.print(result.stderr)

        # Calculate checksum
        checksum = None
        if out_file.exists():
            from .artifacts import calculate_checksum

            checksum = calculate_checksum(out_file)

        return PlanResult(
            exit_code=0 if success else result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            command=result.command,
            has_changes=has_changes,
            plan_file=out_file if out_file.exists() else None,
            checksum=checksum,
        )

    def apply(self, plan_file: Path | None = None) -> ApplyResult:
        """
        Run terraform apply.

        Args:
            plan_file: Path to saved plan file. If None, applies directly.

        Returns:
            ApplyResult with exit code and output.
        """
        console.print("\n[bold blue]🚀 Terraform Apply[/bold blue]")

        args = ["terraform", "apply", TF_INPUT_FALSE, "-auto-approve"]

        if plan_file and plan_file.exists():
            args.append(str(plan_file))
        else:
            # Direct apply - add var files
            for var_file in self.var_files:
                args.extend(["-var-file", var_file])
            # Add custom apply args
            args.extend(self.apply_args)

        # Use tfcmt if available
        if self.use_tfcmt and self._tfcmt_available():
            result = self._run_with_tfcmt("apply", args)
        else:
            result = self._run_command(args)

        if result.success:
            console.print("[green]✅ Apply successful[/green]")
        else:
            console.print("[red]❌ Apply failed[/red]")
            console.print(result.stderr)

        return ApplyResult(
            exit_code=result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            command=result.command,
        )

    def _tfcmt_available(self) -> bool:
        """Check if tfcmt is installed."""
        try:
            result = subprocess.run(  # nosec B603 B607 - tfcmt version check
                ["tfcmt", "--version"],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _run_with_tfcmt(self, operation: str, tf_args: list[str]) -> CommandResult:
        """Run terraform command wrapped with tfcmt for PR comments."""
        if not self.github_token or not self.repo or not self.pr_number:
            # Fall back to direct execution
            return self._run_command(tf_args)

        # tfcmt wraps terraform and posts results to PR
        args = [
            "tfcmt",
            "-owner",
            self.repo.split("/")[0],
            "-repo",
            self.repo.split("/")[1],
            "-pr",
            str(self.pr_number),
            operation,
            "--",
        ] + tf_args

        env = {"GITHUB_TOKEN": self.github_token}
        return self._run_command(args, env=env)
