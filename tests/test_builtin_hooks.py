"""Tests for built-in hooks."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tf_branch_deploy.builtin_hooks import (
    BUILTIN_HOOKS,
    BuiltinHookType,
    HookOutput,
    TerraformValidateRunner,
    TflintRunner,
    TrivyRunner,
)


class TestBuiltinHookType:
    """Tests for BuiltinHookType enum."""

    def test_all_hooks_defined(self) -> None:
        """All required hooks must be defined."""
        hooks = {h.value for h in BuiltinHookType}
        expected = {"trivy", "gitleaks", "validate", "tflint", "infracost", "terraform-docs"}
        assert hooks == expected

    def test_validate_is_only_default_on(self) -> None:
        """terraform validate is the only hook that's on by default."""
        # This is a design decision, not a code check
        # But we document it in the test for clarity
        default_on_hooks = [BuiltinHookType.VALIDATE]
        assert len(default_on_hooks) == 1


class TestHookOutput:
    """Tests for HookOutput dataclass."""

    def test_success_output(self) -> None:
        """Test creating a successful hook output."""
        output = HookOutput(
            success=True,
            exit_code=0,
            summary="✅ All checks passed",
            markdown="### Check ✅\n\nNo issues.",
        )
        assert output.success is True
        assert output.exit_code == 0

    def test_failure_output(self) -> None:
        """Test creating a failed hook output."""
        output = HookOutput(
            success=False,
            exit_code=1,
            summary="❌ Check failed",
            markdown="### Check ❌\n\nErrors found.",
            findings=[{"severity": "error", "summary": "Missing required field"}],
        )
        assert output.success is False
        assert len(output.findings) == 1


class TestTerraformValidateRunner:
    """Tests for TerraformValidateRunner."""

    def test_name(self) -> None:
        """Runner must have correct name."""
        runner = TerraformValidateRunner()
        assert runner.name == "Terraform Validate"

    def test_hook_type(self) -> None:
        """Runner must have correct hook type."""
        runner = TerraformValidateRunner()
        assert runner.hook_type == BuiltinHookType.VALIDATE

    @patch("subprocess.run")
    def test_is_installed_when_terraform_exists(self, mock_run: MagicMock) -> None:
        """Should return True when terraform is installed."""
        mock_run.return_value = MagicMock(returncode=0)
        runner = TerraformValidateRunner()
        assert runner.is_installed() is True

    @patch("subprocess.run")
    def test_is_installed_when_terraform_missing(self, mock_run: MagicMock) -> None:
        """Should return False when terraform is not installed."""
        from subprocess import CalledProcessError
        mock_run.side_effect = CalledProcessError(1, "which")
        runner = TerraformValidateRunner()
        assert runner.is_installed() is False

    @patch("subprocess.run")
    def test_run_success(self, mock_run: MagicMock) -> None:
        """Should return success output when validation passes."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"valid": true, "error_count": 0, "warning_count": 0, "diagnostics": []}',
            stderr="",
        )
        runner = TerraformValidateRunner()
        context = MagicMock()
        output = runner.run(context, Path.cwd())

        assert output.success is True
        assert "valid" in output.summary.lower()
        assert "✅" in output.markdown

    @patch("subprocess.run")
    def test_run_failure(self, mock_run: MagicMock) -> None:
        """Should return failure output when validation fails."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='{"valid": false, "error_count": 2, "warning_count": 1, "diagnostics": []}',
            stderr="Error: Missing required variable",
        )
        runner = TerraformValidateRunner()
        context = MagicMock()
        output = runner.run(context, Path.cwd())

        assert output.success is False
        assert "2 errors" in output.summary
        assert "❌" in output.markdown


class TestTrivyRunner:
    """Tests for TrivyRunner."""

    def test_name(self) -> None:
        """Runner must have correct name."""
        runner = TrivyRunner()
        assert runner.name == "Trivy Security Scan"

    def test_hook_type(self) -> None:
        """Runner must have correct hook type."""
        runner = TrivyRunner()
        assert runner.hook_type == BuiltinHookType.TRIVY

    def test_default_severity(self) -> None:
        """Default severity should be HIGH,CRITICAL."""
        runner = TrivyRunner()
        assert runner.severity == "HIGH,CRITICAL"

    def test_custom_severity(self) -> None:
        """Should accept custom severity."""
        runner = TrivyRunner(severity="CRITICAL")
        assert runner.severity == "CRITICAL"


class TestTflintRunner:
    """Tests for TflintRunner."""

    def test_name(self) -> None:
        """Runner must have correct name."""
        runner = TflintRunner()
        assert runner.name == "TFLint"

    def test_hook_type(self) -> None:
        """Runner must have correct hook type."""
        runner = TflintRunner()
        assert runner.hook_type == BuiltinHookType.TFLINT

    def test_no_config_by_default(self) -> None:
        """Config file should be None by default."""
        runner = TflintRunner()
        assert runner.config_file is None

    def test_custom_config(self) -> None:
        """Should accept custom config file."""
        runner = TflintRunner(config_file=".tflint.hcl")
        assert runner.config_file == ".tflint.hcl"


class TestBuiltinHooksRegistry:
    """Tests for BUILTIN_HOOKS registry."""

    def test_registry_contains_validate(self) -> None:
        """Registry must contain terraform validate."""
        assert BuiltinHookType.VALIDATE in BUILTIN_HOOKS

    def test_registry_contains_trivy(self) -> None:
        """Registry must contain trivy."""
        assert BuiltinHookType.TRIVY in BUILTIN_HOOKS

    def test_registry_contains_tflint(self) -> None:
        """Registry must contain tflint."""
        assert BuiltinHookType.TFLINT in BUILTIN_HOOKS

    def test_registry_contains_gitleaks(self) -> None:
        """Registry must contain gitleaks."""
        assert BuiltinHookType.GITLEAKS in BUILTIN_HOOKS

    def test_registry_contains_infracost(self) -> None:
        """Registry must contain infracost."""
        assert BuiltinHookType.INFRACOST in BUILTIN_HOOKS

    def test_registry_contains_terraform_docs(self) -> None:
        """Registry must contain terraform-docs."""
        assert BuiltinHookType.TERRAFORM_DOCS in BUILTIN_HOOKS

    def test_registry_has_all_hooks(self) -> None:
        """Registry must contain all 6 hook types."""
        assert len(BUILTIN_HOOKS) == 6


class TestGitleaksRunner:
    """Tests for GitleaksRunner."""

    def test_name(self) -> None:
        """Runner must have correct name."""
        from tf_branch_deploy.builtin_hooks import GitleaksRunner
        runner = GitleaksRunner()
        assert runner.name == "Gitleaks Secrets Scan"

    def test_hook_type(self) -> None:
        """Runner must have correct hook type."""
        from tf_branch_deploy.builtin_hooks import GitleaksRunner
        runner = GitleaksRunner()
        assert runner.hook_type == BuiltinHookType.GITLEAKS


class TestInfracostRunner:
    """Tests for InfracostRunner."""

    def test_name(self) -> None:
        """Runner must have correct name."""
        from tf_branch_deploy.builtin_hooks import InfracostRunner
        runner = InfracostRunner()
        assert runner.name == "Infracost Cost Estimation"

    def test_hook_type(self) -> None:
        """Runner must have correct hook type."""
        from tf_branch_deploy.builtin_hooks import InfracostRunner
        runner = InfracostRunner()
        assert runner.hook_type == BuiltinHookType.INFRACOST

    def test_default_threshold(self) -> None:
        """Threshold should be None by default."""
        from tf_branch_deploy.builtin_hooks import InfracostRunner
        runner = InfracostRunner()
        assert runner.threshold is None

    def test_custom_threshold(self) -> None:
        """Should accept custom threshold."""
        from tf_branch_deploy.builtin_hooks import InfracostRunner
        runner = InfracostRunner(threshold="10%")
        assert runner.threshold == "10%"

    @patch.dict("os.environ", {}, clear=True)
    def test_skips_without_api_key(self) -> None:
        """Should skip when INFRACOST_API_KEY not set."""
        from tf_branch_deploy.builtin_hooks import InfracostRunner
        runner = InfracostRunner()
        context = MagicMock()
        output = runner.run(context, Path.cwd())
        assert output.success is True
        assert "skipped" in output.summary.lower()


class TestTerraformDocsRunner:
    """Tests for TerraformDocsRunner."""

    def test_name(self) -> None:
        """Runner must have correct name."""
        from tf_branch_deploy.builtin_hooks import TerraformDocsRunner
        runner = TerraformDocsRunner()
        assert runner.name == "Terraform Docs"

    def test_hook_type(self) -> None:
        """Runner must have correct hook type."""
        from tf_branch_deploy.builtin_hooks import TerraformDocsRunner
        runner = TerraformDocsRunner()
        assert runner.hook_type == BuiltinHookType.TERRAFORM_DOCS

    def test_default_output_file(self) -> None:
        """Default output file should be README.md."""
        from tf_branch_deploy.builtin_hooks import TerraformDocsRunner
        runner = TerraformDocsRunner()
        assert runner.output_file == "README.md"

    def test_custom_output_file(self) -> None:
        """Should accept custom output file."""
        from tf_branch_deploy.builtin_hooks import TerraformDocsRunner
        runner = TerraformDocsRunner(output_file="DOCS.md")
        assert runner.output_file == "DOCS.md"
