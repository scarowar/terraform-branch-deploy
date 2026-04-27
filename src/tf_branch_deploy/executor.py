"""
Terraform executor module.

Handles terraform init, plan, and apply operations with proper
argument resolution and PR comment posting via tfcmt.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - subprocess is required to run terraform
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

TF_INPUT_FALSE = "-input=false"

console = Console()


def _redact_single_arg(arg: str) -> str:
    """Redact a single arg if it contains a -var= value."""
    if arg.startswith("-var="):
        eq_pos = arg.find("=", 5)
        if eq_pos != -1:
            return arg[: eq_pos + 1] + "***"
    return arg


def _redact_args(args: list[str]) -> str:
    """Join args for display, redacting -var= values.

    Handles both ``-var=key=value`` (single token) and
    ``-var key=value`` (two-token) forms, including values that
    contain spaces.
    """
    redacted: list[str] = []
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            redacted.append("***")
            skip_next = False
            continue
        redacted_arg = _redact_single_arg(arg)
        if redacted_arg != arg:
            redacted.append(redacted_arg)
        elif arg == "-var" and i + 1 < len(args):
            redacted.append(arg)
            skip_next = True
        else:
            redacted.append(arg)
    return " ".join(redacted)


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
    """Executes terraform init, plan, and apply operations."""

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

    use_tfcmt: bool = True
    dry_run: bool = False

    def version(self) -> str:
        """Get the installed Terraform version string.

        Returns:
            Semantic version string (e.g., "1.9.8") or "unknown" on failure.
        """
        result = self._run_command(["terraform", "version", "-json"])
        if result.success:
            try:
                version_info = json.loads(result.stdout)
                return version_info.get("terraform_version", "unknown")
            except (json.JSONDecodeError, KeyError):
                pass
        return "unknown"

    def _run_command(
        self,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        """Run a command and capture output."""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        console.print(f"[dim]$ {_redact_args(args)}[/dim]")

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

        for backend in self.backend_configs:
            args.extend(["-backend-config", backend])

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

        # Resolve relative paths against working_directory so .exists()
        # checks the correct location (terraform writes relative to cwd).
        resolved_out = out_file if out_file.is_absolute() else self.working_directory / out_file

        args = ["terraform", "plan", TF_INPUT_FALSE, "-detailed-exitcode"]

        for var_file in self.var_files:
            args.extend(["-var-file", var_file])

        args.extend(["-out", str(out_file)])
        args.extend(self.plan_args)

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

        # Calculate checksum using resolved path
        checksum = None
        if resolved_out.exists():
            from .artifacts import calculate_checksum

            checksum = calculate_checksum(resolved_out)

        return PlanResult(
            exit_code=0 if success else result.exit_code,
            stdout=result.stdout,
            stderr=result.stderr,
            command=result.command,
            has_changes=has_changes,
            plan_file=resolved_out if resolved_out.exists() else None,
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

        # Resolve plan_file for existence check. The plan_file may be:
        # 1. An absolute path (e.g., /repo/terraform/modules/tfplan-int-abc.tfplan)
        # 2. A relative path (resolved against working_directory)
        # 3. A bare filename (e.g., tfplan-int-abc.tfplan) — legacy callers
        # In all cases, we resolve to an absolute path for the exists() check,
        # then derive the path relative to working_directory for the terraform
        # command (since subprocess runs with cwd=working_directory).
        if plan_file:
            if plan_file.is_absolute():
                resolved_plan = plan_file
            else:
                resolved_plan = (self.working_directory / plan_file).resolve()
        else:
            resolved_plan = None

        if resolved_plan and resolved_plan.exists():
            # Pass just the filename to terraform (it runs in working_directory)
            try:
                relative_plan = resolved_plan.relative_to(self.working_directory.resolve())
            except ValueError:
                relative_plan = resolved_plan
            args.append(str(relative_plan))
        elif plan_file is not None:
            # A plan file was explicitly requested but not found — abort.
            # Never silently fall through to an untargeted apply.
            msg = (
                f"Plan file '{plan_file}' not found "
                f"(resolved: '{resolved_plan}'). "
                "Refusing to run untargeted apply."
            )
            console.print(f"[red]❌ {msg}[/red]")
            return ApplyResult(
                exit_code=1,
                stdout="",
                stderr=msg,
                command=["terraform", "apply", "(aborted)"],
            )
        else:
            # No plan file requested (e.g. rollback) — apply with var-files
            for var_file in self.var_files:
                args.extend(["-var-file", var_file])
            args.extend(self.apply_args)

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
            return self._run_command(tf_args)

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
