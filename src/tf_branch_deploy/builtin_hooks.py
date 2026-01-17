"""
Built-in hooks for terraform-branch-deploy.

This module provides curated, first-class hooks that ship with the action.
Users configure them via .tf-branch-deploy.yml, not shell commands.

Architecture:
- All hooks are opt-in EXCEPT terraform validate (on by default)
- Hooks post structured PR comments
- Hooks support: enabled, fail-on-error, severity thresholds
"""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from .hooks import HookContext

console = Console()


class BuiltinHookType(str, Enum):
    """Available built-in hooks."""

    # Pre-init: Security
    TRIVY = "trivy"
    GITLEAKS = "gitleaks"

    # Pre-plan: Quality
    VALIDATE = "validate"  # terraform validate (DEFAULT ON)
    TFLINT = "tflint"

    # Post-plan: Analysis
    INFRACOST = "infracost"

    # Post-apply: Documentation
    TERRAFORM_DOCS = "terraform-docs"


@dataclass
class HookOutput:
    """Structured output from a built-in hook."""

    success: bool
    exit_code: int
    summary: str  # One-line summary for logs
    markdown: str  # Full markdown for PR comment
    findings: list[dict] = field(default_factory=list)  # Structured findings


class BuiltinHookRunner(ABC):
    """Base class for built-in hooks."""

    @abstractmethod
    def run(self, context: "HookContext", working_dir: Path) -> HookOutput:
        """Execute the hook and return structured output."""
        pass

    @abstractmethod
    def is_installed(self) -> bool:
        """Check if the tool is available."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable hook name."""
        pass

    @property
    @abstractmethod
    def hook_type(self) -> BuiltinHookType:
        """Hook type enum value."""
        pass

    def _check_command_exists(self, command: str) -> bool:
        """Check if a command is available in PATH."""
        try:
            subprocess.run(
                ["which", command],
                capture_output=True,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False


class TerraformValidateRunner(BuiltinHookRunner):
    """
    Run terraform validate.

    This is the ONLY hook that runs by default.
    It is a first-class Terraform command and foundational safety check.
    """

    @property
    def name(self) -> str:
        return "Terraform Validate"

    @property
    def hook_type(self) -> BuiltinHookType:
        return BuiltinHookType.VALIDATE

    def is_installed(self) -> bool:
        return self._check_command_exists("terraform")

    def run(self, context: "HookContext", working_dir: Path) -> HookOutput:
        console.print(f"  [dim]Running terraform validate in {working_dir}[/dim]")

        try:
            result = subprocess.run(
                ["terraform", "validate", "-json"],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )

            import json

            try:
                output = json.loads(result.stdout)
                valid = output.get("valid", False)
                error_count = output.get("error_count", 0)
                warning_count = output.get("warning_count", 0)
                diagnostics = output.get("diagnostics", [])
            except json.JSONDecodeError:
                valid = result.returncode == 0
                error_count = 1 if not valid else 0
                warning_count = 0
                diagnostics = []

            if valid:
                summary = "✅ Terraform configuration is valid"
                markdown = """### Terraform Validate ✅

Configuration is valid. No errors or warnings."""
            else:
                summary = f"❌ Terraform validate failed: {error_count} errors, {warning_count} warnings"
                markdown = f"""### Terraform Validate ❌

| Severity | Count |
|----------|-------|
| Errors | {error_count} |
| Warnings | {warning_count} |

<details>
<summary>Diagnostics</summary>

```
{result.stderr or result.stdout}
```

</details>"""

            return HookOutput(
                success=valid,
                exit_code=result.returncode,
                summary=summary,
                markdown=markdown,
                findings=[
                    {"severity": d.get("severity", "error"), "summary": d.get("summary", "")}
                    for d in diagnostics
                ],
            )

        except subprocess.TimeoutExpired:
            return HookOutput(
                success=False,
                exit_code=124,
                summary="❌ Terraform validate timed out",
                markdown="### Terraform Validate ⏱️\n\nValidation timed out after 300 seconds.",
            )
        except Exception as e:
            return HookOutput(
                success=False,
                exit_code=1,
                summary=f"❌ Terraform validate error: {e}",
                markdown=f"### Terraform Validate ❌\n\nError: {e}",
            )


class TrivyRunner(BuiltinHookRunner):
    """
    Run Trivy security scanner.

    Scans for vulnerabilities, misconfigurations, and secrets.
    """

    def __init__(self, severity: str = "HIGH,CRITICAL"):
        self.severity = severity

    @property
    def name(self) -> str:
        return "Trivy Security Scan"

    @property
    def hook_type(self) -> BuiltinHookType:
        return BuiltinHookType.TRIVY

    def is_installed(self) -> bool:
        return self._check_command_exists("trivy")

    def run(self, context: "HookContext", working_dir: Path) -> HookOutput:
        console.print(f"  [dim]Running trivy in {working_dir}[/dim]")

        try:
            result = subprocess.run(
                [
                    "trivy",
                    "fs",
                    "--security-checks",
                    "vuln,secret,config",
                    "--severity",
                    self.severity,
                    "--format",
                    "json",
                    ".",
                ],
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=600,
            )

            import json

            try:
                output = json.loads(result.stdout)
                results = output.get("Results", [])
                vuln_count = sum(
                    len(r.get("Vulnerabilities", [])) for r in results
                )
                secret_count = sum(len(r.get("Secrets", [])) for r in results)
                misconfig_count = sum(
                    len(r.get("Misconfigurations", [])) for r in results
                )
                total = vuln_count + secret_count + misconfig_count
            except json.JSONDecodeError:
                total = 0 if result.returncode == 0 else 1
                vuln_count = secret_count = misconfig_count = 0

            success = result.returncode == 0

            if success:
                summary = "✅ No security issues found"
                markdown = """### Trivy Security Scan ✅

No vulnerabilities, secrets, or misconfigurations detected."""
            else:
                summary = f"❌ Found {total} security issues"
                markdown = f"""### Trivy Security Scan ❌

| Type | Count |
|------|-------|
| Vulnerabilities | {vuln_count} |
| Secrets | {secret_count} |
| Misconfigurations | {misconfig_count} |

<details>
<summary>Details</summary>

```
{result.stderr}
```

</details>"""

            return HookOutput(
                success=success,
                exit_code=result.returncode,
                summary=summary,
                markdown=markdown,
            )

        except subprocess.TimeoutExpired:
            return HookOutput(
                success=False,
                exit_code=124,
                summary="❌ Trivy timed out",
                markdown="### Trivy Security Scan ⏱️\n\nScan timed out after 600 seconds.",
            )
        except Exception as e:
            return HookOutput(
                success=False,
                exit_code=1,
                summary=f"❌ Trivy error: {e}",
                markdown=f"### Trivy Security Scan ❌\n\nError: {e}",
            )


class TflintRunner(BuiltinHookRunner):
    """
    Run TFLint.

    Terraform linter for best practices and conventions.
    """

    def __init__(self, config_file: str | None = None):
        self.config_file = config_file

    @property
    def name(self) -> str:
        return "TFLint"

    @property
    def hook_type(self) -> BuiltinHookType:
        return BuiltinHookType.TFLINT

    def is_installed(self) -> bool:
        return self._check_command_exists("tflint")

    def run(self, context: "HookContext", working_dir: Path) -> HookOutput:
        console.print(f"  [dim]Running tflint in {working_dir}[/dim]")

        cmd = ["tflint", "--format", "json"]
        if self.config_file:
            cmd.extend(["--config", self.config_file])

        try:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )

            import json

            try:
                output = json.loads(result.stdout)
                issues = output.get("issues", [])
                error_count = sum(1 for i in issues if i.get("rule", {}).get("severity") == "error")
                warning_count = sum(1 for i in issues if i.get("rule", {}).get("severity") == "warning")
            except json.JSONDecodeError:
                issues = []
                error_count = 1 if result.returncode != 0 else 0
                warning_count = 0

            success = result.returncode == 0

            if success:
                summary = "✅ No linting issues"
                markdown = """### TFLint ✅

No issues found."""
            else:
                summary = f"⚠️ Found {len(issues)} linting issues"
                markdown = f"""### TFLint ⚠️

| Severity | Count |
|----------|-------|
| Errors | {error_count} |
| Warnings | {warning_count} |

<details>
<summary>Details</summary>

```
{result.stdout}
```

</details>"""

            return HookOutput(
                success=success,
                exit_code=result.returncode,
                summary=summary,
                markdown=markdown,
            )

        except subprocess.TimeoutExpired:
            return HookOutput(
                success=False,
                exit_code=124,
                summary="❌ TFLint timed out",
                markdown="### TFLint ⏱️\n\nLinting timed out after 300 seconds.",
            )
        except Exception as e:
            return HookOutput(
                success=False,
                exit_code=1,
                summary=f"❌ TFLint error: {e}",
                markdown=f"### TFLint ❌\n\nError: {e}",
            )


# Registry of built-in hooks
BUILTIN_HOOKS: dict[BuiltinHookType, type[BuiltinHookRunner]] = {
    BuiltinHookType.VALIDATE: TerraformValidateRunner,
    BuiltinHookType.TRIVY: TrivyRunner,
    BuiltinHookType.TFLINT: TflintRunner,
}
