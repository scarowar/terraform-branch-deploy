"""Unit tests for the Terraform executor module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tf_branch_deploy.executor import (
    ApplyResult,
    CommandResult,
    PlanResult,
    TerraformExecutor,
)


@pytest.fixture
def executor(tmp_path: Path) -> TerraformExecutor:
    """Create a test executor with dry_run enabled."""
    return TerraformExecutor(
        working_directory=tmp_path,
        var_files=["common.tfvars", "dev.tfvars"],
        backend_configs=["backends/dev.tfbackend"],
        init_args=["-upgrade"],
        plan_args=["-compact-warnings"],
        apply_args=["-parallelism=5"],
        dry_run=True,
    )


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_when_exit_code_zero(self) -> None:
        result = CommandResult(exit_code=0, stdout="", stderr="", command=["ls"])
        assert result.success is True

    def test_failure_when_exit_code_nonzero(self) -> None:
        result = CommandResult(exit_code=1, stdout="", stderr="error", command=["ls"])
        assert result.success is False


class TestPlanResult:
    """Tests for PlanResult dataclass."""

    def test_has_changes_default_false(self) -> None:
        result = PlanResult(exit_code=0, stdout="", stderr="", command=[])
        assert result.has_changes is False

    def test_plan_file_default_none(self) -> None:
        result = PlanResult(exit_code=0, stdout="", stderr="", command=[])
        assert result.plan_file is None


class TestTerraformExecutor:
    """Tests for TerraformExecutor class."""

    def test_constructor_sets_fields(self, tmp_path: Path) -> None:
        executor = TerraformExecutor(
            working_directory=tmp_path,
            var_files=["a.tfvars"],
            backend_configs=["b.tfbackend"],
        )
        assert executor.working_directory == tmp_path
        assert executor.var_files == ["a.tfvars"]
        assert executor.backend_configs == ["b.tfbackend"]

    def test_dry_run_flag(self, executor: TerraformExecutor) -> None:
        """Executor can be created with dry_run=True."""
        assert executor.dry_run is True

    @patch("subprocess.run")
    def test_run_command_captures_output(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """_run_command captures stdout and stderr."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="success output",
            stderr="",
        )

        result = executor._run_command(["echo", "test"])

        assert result.exit_code == 0
        assert result.stdout == "success output"
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_init_builds_correct_command(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """init() builds correct terraform command with backend configs."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        executor.init()

        # Check the command that was run
        call_args = mock_run.call_args
        args = call_args[0][0]

        assert args[0] == "terraform"
        assert args[1] == "init"
        assert "-input=false" in args
        assert "-backend-config" in args
        assert "backends/dev.tfbackend" in args
        assert "-upgrade" in args

    @patch("subprocess.run")
    def test_plan_builds_correct_command(
        self, mock_run: MagicMock, executor: TerraformExecutor, tmp_path: Path
    ) -> None:
        """plan() builds correct terraform command with var files."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        out_file = tmp_path / "plan.tfplan"
        executor.plan(out_file=out_file)

        call_args = mock_run.call_args
        args = call_args[0][0]

        assert args[0] == "terraform"
        assert args[1] == "plan"
        assert "-input=false" in args
        assert "-detailed-exitcode" in args
        assert "-var-file" in args
        assert "common.tfvars" in args
        assert "-out" in args
        assert "-compact-warnings" in args

    @patch("subprocess.run")
    def test_plan_exit_code_2_means_changes(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """Terraform plan exit code 2 means changes are present."""
        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="")

        result = executor.plan()

        assert result.has_changes is True
        assert result.success is True  # Exit code 2 is success with changes

    @patch("subprocess.run")
    def test_plan_exit_code_0_means_no_changes(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """Terraform plan exit code 0 means no changes."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        result = executor.plan()

        assert result.has_changes is False
        assert result.success is True

    @patch("subprocess.run")
    def test_apply_builds_correct_command(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """apply() builds correct terraform command."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        executor.apply()

        call_args = mock_run.call_args
        args = call_args[0][0]

        assert args[0] == "terraform"
        assert args[1] == "apply"
        assert "-input=false" in args
        assert "-auto-approve" in args
        assert "-var-file" in args
        assert "-parallelism=5" in args

    @patch("subprocess.run")
    def test_apply_with_plan_file(
        self, mock_run: MagicMock, executor: TerraformExecutor, tmp_path: Path
    ) -> None:
        """apply() uses plan file when provided."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        plan_file = tmp_path / "plan.tfplan"
        plan_file.write_bytes(b"plan content")

        executor.apply(plan_file=plan_file)

        call_args = mock_run.call_args
        args = call_args[0][0]

        assert str(plan_file) in args
        # Var files should NOT be in command when using plan file
        assert "-var-file" not in args


class TestTfcmtIntegration:
    """Tests for tfcmt integration."""

    def test_tfcmt_not_available(self, executor: TerraformExecutor) -> None:
        """When tfcmt is not installed, returns False."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            assert executor._tfcmt_available() is False

    def test_tfcmt_available(self, executor: TerraformExecutor) -> None:
        """When tfcmt is installed, returns True."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert executor._tfcmt_available() is True

    def test_run_with_tfcmt_falls_back_without_credentials(
        self, executor: TerraformExecutor
    ) -> None:
        """Falls back to direct execution without GitHub credentials."""
        with patch.object(executor, "_run_command") as mock_run:
            mock_run.return_value = CommandResult(0, "", "", [])

            executor._run_with_tfcmt("plan", ["terraform", "plan"])

            # Should call _run_command directly with terraform args
            call_args = mock_run.call_args[0][0]
            assert call_args == ["terraform", "plan"]
