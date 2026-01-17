"""
Hook runner module.

Handles execution of lifecycle hooks with:
- Phase-based execution (pre-init, post-init, pre-plan, post-plan, post-apply)
- Condition filtering (always, plan-only, apply-only, rollback-only)
- Timeout enforcement
- Fail-on-error semantics
"""

from __future__ import annotations

import os
import signal
import subprocess  # nosec B404 - subprocess is required to run hooks
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from .config import Hook, HooksConfig

console = Console()


class HookPhase(str, Enum):
    """Execution phase for hooks."""

    PRE_INIT = "pre-init"
    POST_INIT = "post-init"
    PRE_PLAN = "pre-plan"
    POST_PLAN = "post-plan"
    POST_APPLY = "post-apply"


@dataclass
class HookResult:
    """Result of hook execution."""

    name: str
    phase: HookPhase
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def failed(self) -> bool:
        return not self.success and not self.skipped


@dataclass
class HookContext:
    """Context available to hooks via environment variables."""

    phase: HookPhase
    environment: str
    operation: str  # plan, apply, rollback
    is_rollback: bool
    sha: str
    ref: str
    actor: str
    pr_number: str
    params: str
    working_dir: Path
    is_production: bool
    plan_file: str | None = None  # Only for post-plan
    has_changes: bool | None = None  # Only for post-plan

    def to_env(self) -> dict[str, str]:
        """Convert context to TF_BD_* environment variables."""
        env = {
            "TF_BD_PHASE": self.phase.value,
            "TF_BD_ENVIRONMENT": self.environment,
            "TF_BD_OPERATION": self.operation,
            "TF_BD_IS_ROLLBACK": str(self.is_rollback).lower(),
            "TF_BD_SHA": self.sha,
            "TF_BD_REF": self.ref,
            "TF_BD_ACTOR": self.actor,
            "TF_BD_PR_NUMBER": self.pr_number,
            "TF_BD_PARAMS": self.params,
            "TF_BD_WORKING_DIR": str(self.working_dir),
            "TF_BD_IS_PRODUCTION": str(self.is_production).lower(),
        }
        if self.plan_file is not None:
            env["TF_BD_PLAN_FILE"] = self.plan_file
        if self.has_changes is not None:
            env["TF_BD_HAS_CHANGES"] = str(self.has_changes).lower()
        return env


@dataclass
class HookRunner:
    """Runs lifecycle hooks with proper phase ordering and condition filtering."""

    hooks_config: "HooksConfig | None"
    working_directory: Path = field(default_factory=lambda: Path.cwd())

    def run_phase(
        self,
        phase: HookPhase,
        context: HookContext,
    ) -> list[HookResult]:
        """
        Run all hooks for a given phase.

        Args:
            phase: The execution phase (pre-init, post-plan, etc.)
            context: Context with environment, operation, etc.

        Returns:
            List of HookResult for each hook.
            Stops on first failure if fail-on-error=true.
        """
        if self.hooks_config is None:
            return []

        hooks = self._get_hooks_for_phase(phase)
        if not hooks:
            return []

        console.print(f"\n[bold cyan]🔧 Running {phase.value} hooks[/bold cyan]")

        results: list[HookResult] = []
        for hook in hooks:
            if not self._should_run_hook(hook, context):
                result = HookResult(
                    name=hook.name,
                    phase=phase,
                    exit_code=0,
                    stdout="",
                    stderr="",
                    skipped=True,
                    skip_reason=f"Condition '{hook.condition.value}' not met for operation '{context.operation}'",
                )
                results.append(result)
                console.print(f"  [dim]⏭️  {hook.name} (skipped: {result.skip_reason})[/dim]")
                continue

            result = self._run_hook(hook, phase, context)
            results.append(result)

            if result.failed and hook.fail_on_error:
                console.print(f"  [red]❌ {hook.name} failed (blocking)[/red]")
                break
            elif result.failed:
                console.print(f"  [yellow]⚠️  {hook.name} failed (non-blocking)[/yellow]")
            else:
                console.print(f"  [green]✅ {hook.name}[/green]")

        return results

    def _get_hooks_for_phase(self, phase: HookPhase) -> list["Hook"]:
        """Get hooks configured for a specific phase."""
        if self.hooks_config is None:
            return []

        phase_map = {
            HookPhase.PRE_INIT: self.hooks_config.pre_init,
            HookPhase.POST_INIT: self.hooks_config.post_init,
            HookPhase.PRE_PLAN: self.hooks_config.pre_plan,
            HookPhase.POST_PLAN: self.hooks_config.post_plan,
            HookPhase.POST_APPLY: self.hooks_config.post_apply,
        }
        return phase_map.get(phase, [])

    def _should_run_hook(self, hook: "Hook", context: HookContext) -> bool:
        """Determine if a hook should run based on its condition."""
        from .config import HookCondition

        condition = hook.condition
        operation = context.operation

        if condition == HookCondition.ALWAYS:
            return True
        elif condition == HookCondition.PLAN_ONLY:
            return operation == "plan"
        elif condition == HookCondition.APPLY_ONLY:
            return operation in ("apply", "rollback")
        elif condition == HookCondition.ROLLBACK_ONLY:
            return context.is_rollback
        else:
            return True  # Default to running

    def _run_hook(
        self,
        hook: "Hook",
        phase: HookPhase,
        context: HookContext,
    ) -> HookResult:
        """Execute a single hook with timeout enforcement."""
        # Build environment
        env = os.environ.copy()
        env.update(context.to_env())
        if hook.env:
            env.update(hook.env)

        # Determine working directory
        cwd = (
            Path(hook.working_directory)
            if hook.working_directory
            else self.working_directory
        )

        console.print(f"  [dim]Running: {hook.name}[/dim]")

        try:
            result = subprocess.run(  # nosec B603 B602 - user-defined hooks
                hook.run,
                shell=True,  # nosec B602 - shell required for user scripts
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=hook.timeout,
                env=env,
            )
            return HookResult(
                name=hook.name,
                phase=phase,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except subprocess.TimeoutExpired as e:
            return HookResult(
                name=hook.name,
                phase=phase,
                exit_code=124,  # Standard timeout exit code
                stdout=e.stdout or "" if hasattr(e, "stdout") else "",
                stderr=f"Hook timed out after {hook.timeout} seconds",
                timed_out=True,
            )
        except Exception as e:
            return HookResult(
                name=hook.name,
                phase=phase,
                exit_code=1,
                stdout="",
                stderr=str(e),
            )

    def has_blocking_failure(self, results: list[HookResult]) -> bool:
        """Check if any hook failed with fail-on-error=true."""
        # The last result with failed=True indicates a blocking failure
        # since we stop on first blocking failure in run_phase
        return any(r.failed for r in results)
