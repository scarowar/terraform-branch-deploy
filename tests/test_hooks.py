"""Tests for HookRunner module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tf_branch_deploy.config import Hook, HookCondition, HooksConfig
from tf_branch_deploy.hooks import HookContext, HookPhase, HookResult, HookRunner


class TestHookPhase:
    """Tests for HookPhase enum."""

    def test_all_phases_defined(self) -> None:
        """All required phases must be defined."""
        phases = {p.value for p in HookPhase}
        expected = {"pre-init", "post-init", "pre-plan", "post-plan", "post-apply"}
        assert phases == expected


class TestHookContext:
    """Tests for HookContext dataclass."""

    def test_to_env_basic(self) -> None:
        """Context should convert to TF_BD_* environment variables."""
        ctx = HookContext(
            phase=HookPhase.PRE_INIT,
            environment="dev",
            operation="apply",
            is_rollback=False,
            sha="abc123",
            ref="feature/test",
            actor="testuser",
            pr_number="42",
            params="-target=module.foo",
            working_dir=Path("/app"),
            is_production=False,
        )
        env = ctx.to_env()

        assert env["TF_BD_PHASE"] == "pre-init"
        assert env["TF_BD_ENVIRONMENT"] == "dev"
        assert env["TF_BD_OPERATION"] == "apply"
        assert env["TF_BD_IS_ROLLBACK"] == "false"
        assert env["TF_BD_SHA"] == "abc123"
        assert env["TF_BD_REF"] == "feature/test"
        assert env["TF_BD_ACTOR"] == "testuser"
        assert env["TF_BD_PR_NUMBER"] == "42"
        assert env["TF_BD_PARAMS"] == "-target=module.foo"
        assert env["TF_BD_WORKING_DIR"] == "/app"
        assert env["TF_BD_IS_PRODUCTION"] == "false"

    def test_to_env_with_plan_file(self) -> None:
        """Post-plan context should include plan file info."""
        ctx = HookContext(
            phase=HookPhase.POST_PLAN,
            environment="prod",
            operation="plan",
            is_rollback=False,
            sha="def456",
            ref="main",
            actor="admin",
            pr_number="100",
            params="",
            working_dir=Path("/infra"),
            is_production=True,
            plan_file="tfplan-prod-def456.tfplan",
            has_changes=True,
        )
        env = ctx.to_env()

        assert env["TF_BD_IS_PRODUCTION"] == "true"
        assert env["TF_BD_PLAN_FILE"] == "tfplan-prod-def456.tfplan"
        assert env["TF_BD_HAS_CHANGES"] == "true"


class TestHookResult:
    """Tests for HookResult dataclass."""

    def test_success_when_exit_zero(self) -> None:
        """Result is success when exit code is 0."""
        result = HookResult(
            name="test",
            phase=HookPhase.PRE_INIT,
            exit_code=0,
            stdout="ok",
            stderr="",
        )
        assert result.success is True
        assert result.failed is False

    def test_failed_when_exit_nonzero(self) -> None:
        """Result is failed when exit code is non-zero."""
        result = HookResult(
            name="test",
            phase=HookPhase.PRE_INIT,
            exit_code=1,
            stdout="",
            stderr="error",
        )
        assert result.success is False
        assert result.failed is True

    def test_failed_when_timed_out(self) -> None:
        """Result is failed when hook timed out."""
        result = HookResult(
            name="test",
            phase=HookPhase.PRE_INIT,
            exit_code=124,
            stdout="",
            stderr="timeout",
            timed_out=True,
        )
        assert result.success is False
        assert result.failed is True

    def test_skipped_not_failed(self) -> None:
        """Skipped results are not considered failures."""
        result = HookResult(
            name="test",
            phase=HookPhase.PRE_INIT,
            exit_code=0,
            stdout="",
            stderr="",
            skipped=True,
            skip_reason="Condition not met",
        )
        assert result.skipped is True
        assert result.failed is False


class TestHookRunnerConditions:
    """Tests for hook condition filtering."""

    @pytest.fixture
    def context_plan(self) -> HookContext:
        """Context for plan operation."""
        return HookContext(
            phase=HookPhase.PRE_PLAN,
            environment="dev",
            operation="plan",
            is_rollback=False,
            sha="abc123",
            ref="feature/test",
            actor="user",
            pr_number="42",
            params="",
            working_dir=Path.cwd(),
            is_production=False,
        )

    @pytest.fixture
    def context_apply(self) -> HookContext:
        """Context for apply operation."""
        return HookContext(
            phase=HookPhase.PRE_PLAN,
            environment="prod",
            operation="apply",
            is_rollback=False,
            sha="def456",
            ref="feature/deploy",
            actor="deployer",
            pr_number="100",
            params="",
            working_dir=Path.cwd(),
            is_production=True,
        )

    @pytest.fixture
    def context_rollback(self) -> HookContext:
        """Context for rollback operation."""
        return HookContext(
            phase=HookPhase.PRE_PLAN,
            environment="prod",
            operation="rollback",
            is_rollback=True,
            sha="ghi789",
            ref="main",
            actor="admin",
            pr_number="200",
            params="",
            working_dir=Path.cwd(),
            is_production=True,
        )

    def test_condition_always_runs_on_plan(self, context_plan: HookContext) -> None:
        """Condition 'always' should run on plan."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.ALWAYS)
        assert runner._should_run_hook(hook, context_plan) is True

    def test_condition_always_runs_on_apply(self, context_apply: HookContext) -> None:
        """Condition 'always' should run on apply."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.ALWAYS)
        assert runner._should_run_hook(hook, context_apply) is True

    def test_condition_plan_only_runs_on_plan(self, context_plan: HookContext) -> None:
        """Condition 'plan-only' should run on plan."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.PLAN_ONLY)
        assert runner._should_run_hook(hook, context_plan) is True

    def test_condition_plan_only_skips_apply(self, context_apply: HookContext) -> None:
        """Condition 'plan-only' should skip on apply."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.PLAN_ONLY)
        assert runner._should_run_hook(hook, context_apply) is False

    def test_condition_apply_only_runs_on_apply(self, context_apply: HookContext) -> None:
        """Condition 'apply-only' should run on apply."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.APPLY_ONLY)
        assert runner._should_run_hook(hook, context_apply) is True

    def test_condition_apply_only_runs_on_rollback(self, context_rollback: HookContext) -> None:
        """Condition 'apply-only' should run on rollback."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.APPLY_ONLY)
        assert runner._should_run_hook(hook, context_rollback) is True

    def test_condition_apply_only_skips_plan(self, context_plan: HookContext) -> None:
        """Condition 'apply-only' should skip on plan."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.APPLY_ONLY)
        assert runner._should_run_hook(hook, context_plan) is False

    def test_condition_rollback_only_runs_on_rollback(self, context_rollback: HookContext) -> None:
        """Condition 'rollback-only' should run on rollback."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.ROLLBACK_ONLY)
        assert runner._should_run_hook(hook, context_rollback) is True

    def test_condition_rollback_only_skips_apply(self, context_apply: HookContext) -> None:
        """Condition 'rollback-only' should skip on normal apply."""
        runner = HookRunner(hooks_config=None)
        hook = Hook(name="test", run="echo hello", condition=HookCondition.ROLLBACK_ONLY)
        assert runner._should_run_hook(hook, context_apply) is False


class TestHookRunnerExecution:
    """Tests for hook execution."""

    @pytest.fixture
    def simple_hooks_config(self) -> HooksConfig:
        """Simple hooks configuration for testing."""
        return HooksConfig(
            pre_init=[
                Hook(name="Echo Test", run="echo hello")
            ]
        )

    @pytest.fixture
    def context(self) -> HookContext:
        """Basic context for testing."""
        return HookContext(
            phase=HookPhase.PRE_INIT,
            environment="dev",
            operation="plan",
            is_rollback=False,
            sha="abc123",
            ref="feature/test",
            actor="user",
            pr_number="42",
            params="",
            working_dir=Path.cwd(),
            is_production=False,
        )

    def test_run_phase_executes_hooks(
        self, simple_hooks_config: HooksConfig, context: HookContext
    ) -> None:
        """Run phase should execute configured hooks."""
        runner = HookRunner(hooks_config=simple_hooks_config)
        results = runner.run_phase(HookPhase.PRE_INIT, context)

        assert len(results) == 1
        assert results[0].name == "Echo Test"
        assert results[0].success is True

    def test_run_phase_returns_empty_when_no_config(self, context: HookContext) -> None:
        """Run phase should return empty list when no hooks configured."""
        runner = HookRunner(hooks_config=None)
        results = runner.run_phase(HookPhase.PRE_INIT, context)
        assert results == []

    def test_has_blocking_failure_detects_failure(self) -> None:
        """has_blocking_failure should detect failed results."""
        results = [
            HookResult(name="ok", phase=HookPhase.PRE_INIT, exit_code=0, stdout="", stderr=""),
            HookResult(name="fail", phase=HookPhase.PRE_INIT, exit_code=1, stdout="", stderr="error"),
        ]
        runner = HookRunner(hooks_config=None)
        assert runner.has_blocking_failure(results) is True

    def test_has_blocking_failure_no_failures(self) -> None:
        """has_blocking_failure should return False when all succeed."""
        results = [
            HookResult(name="ok1", phase=HookPhase.PRE_INIT, exit_code=0, stdout="", stderr=""),
            HookResult(name="ok2", phase=HookPhase.PRE_INIT, exit_code=0, stdout="", stderr=""),
        ]
        runner = HookRunner(hooks_config=None)
        assert runner.has_blocking_failure(results) is False
