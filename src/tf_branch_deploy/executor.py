"""
Terraform executor module.

Handles terraform init, plan, and apply operations with proper
argument resolution and optional PR comment posting via tfcmt.
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404 - subprocess is required to run terraform
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

TF_INPUT_FALSE = "-input=false"
GITHUB_TOKEN_ENV_VARS = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GH_ENTERPRISE_TOKEN",
    "TFBD_GITHUB_TOKEN",
)

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
    timeout: int = 3600

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
        full_env = self._subprocess_env(env)

        console.print(f"[dim]$ {_redact_args(args)}[/dim]")

        try:
            result = subprocess.run(  # nosec B603 B607 - args from validated config, terraform via PATH is expected
                args,
                cwd=self.working_directory,
                capture_output=True,
                text=True,
                env=full_env,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            console.print(
                f"[red]❌ Command timed out after {self.timeout}s: {_redact_args(args)}[/red]"
            )
            return CommandResult(
                exit_code=124,
                stdout="",
                stderr=f"Command timed out after {self.timeout} seconds",
                command=args,
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
        plan_arg, missing_plan_error = self._plan_arg_for_apply(plan_file)

        if missing_plan_error:
            console.print(f"[red]❌ {missing_plan_error}[/red]")
            return self._aborted_apply(missing_plan_error)

        if plan_arg:
            args.append(plan_arg)
        else:
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

    def _plan_arg_for_apply(self, plan_file: Path | None) -> tuple[str | None, str | None]:
        """Resolve an explicit saved plan into the argument Terraform should receive."""
        if plan_file is None:
            return None, None

        resolved_plan = self._resolve_plan_path(plan_file)
        if not resolved_plan.exists():
            msg = (
                f"Plan file '{plan_file}' not found "
                f"(resolved: '{resolved_plan}'). "
                "Refusing to run untargeted apply."
            )
            return None, msg

        return str(self._terraform_relative_plan_path(resolved_plan)), None

    def _resolve_plan_path(self, plan_file: Path) -> Path:
        """Resolve a user-supplied plan path against the Terraform working directory."""
        if plan_file.is_absolute():
            return plan_file
        return (self.working_directory / plan_file).resolve()

    def _terraform_relative_plan_path(self, resolved_plan: Path) -> Path:
        """Prefer a path relative to Terraform's working directory when possible."""
        try:
            return resolved_plan.relative_to(self.working_directory.resolve())
        except ValueError:
            return resolved_plan

    @staticmethod
    def _aborted_apply(message: str) -> ApplyResult:
        """Return the standard result for an apply rejected before Terraform starts."""
        return ApplyResult(
            exit_code=1,
            stdout="",
            stderr=message,
            command=["terraform", "apply", "(aborted)"],
        )

    def _tfcmt_available(self) -> bool:
        """Check if tfcmt is installed."""
        try:
            result = subprocess.run(  # nosec B603 B607 - tfcmt version check
                ["tfcmt", "--version"],
                capture_output=True,
                text=True,
                env=self._subprocess_env(),
            )
            return result.returncode == 0
        except FileNotFoundError:
            return False

    @staticmethod
    def _subprocess_env(env: dict[str, str] | None = None) -> dict[str, str]:
        """Build a subprocess environment that does not leak GitHub tokens to Terraform."""
        full_env = os.environ.copy()
        for name in GITHUB_TOKEN_ENV_VARS:
            full_env.pop(name, None)
        if env:
            full_env.update(env)
        return full_env

    def _run_with_tfcmt(self, operation: str, tf_args: list[str]) -> CommandResult:
        """Run terraform command wrapped with tfcmt for PR comments."""
        if not self.github_token or not self.repo or not self.pr_number:
            return self._run_command(tf_args)

        scrubbed_tf_args = ["env"]
        for name in GITHUB_TOKEN_ENV_VARS:
            scrubbed_tf_args.extend(["-u", name])
        scrubbed_tf_args.extend(tf_args)

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
        ] + scrubbed_tf_args

        env = {"GITHUB_TOKEN": self.github_token}
        return self._run_command(args, env=env)
