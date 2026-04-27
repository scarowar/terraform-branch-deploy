"""Unit tests for the Terraform executor module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tf_branch_deploy.executor import (
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


class TestTerraformExecutor:
    """Tests for TerraformExecutor class."""

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
    def test_plan_exit_code_1_means_error(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """Terraform plan exit code 1 means error (not changes)."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error!")

        result = executor.plan()

        assert result.has_changes is False
        assert result.success is False

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

        assert plan_file.name in args
        # Var files should NOT be in command when using plan file
        assert "-var-file" not in args

    @patch("subprocess.run")
    def test_apply_with_relative_plan_file_in_working_directory(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """apply() resolves relative plan file path against working_directory.

        Regression test: when a bare filename is passed, the executor must
        resolve it relative to working_directory — not the Python process
        CWD — to find the file.
        """
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Simulate: working_directory = tmp_path/terraform/modules
        working_dir = tmp_path / "terraform" / "modules"
        working_dir.mkdir(parents=True)

        # Plan file exists inside working_directory
        plan_file = working_dir / "tfplan-int-06b61570.tfplan"
        plan_file.write_bytes(b"targeted plan content")

        executor = TerraformExecutor(
            working_directory=working_dir,
            var_files=["../config/int/int_config.tfvars"],
        )

        # Pass only the bare filename (as _apply_with_plan does)
        executor.apply(plan_file=Path(plan_file.name))

        call_args = mock_run.call_args
        args = call_args[0][0]

        # Plan file must be in the command — NOT var-file fallback
        assert plan_file.name in args
        assert "-var-file" not in args, (
            "var-file should NOT appear when a plan file exists — "
            "this means the plan file was not found and a full untargeted apply ran instead"
        )

    @patch("subprocess.run")
    def test_apply_aborts_when_plan_file_provided_but_missing(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """apply() aborts when plan_file is provided but does not exist.

        Regression test: a missing plan file must NEVER silently fall through
        to an untargeted 'terraform apply -auto-approve'. The executor must
        abort and return a failure exit code.
        """
        working_dir = tmp_path / "terraform" / "modules"
        working_dir.mkdir(parents=True)

        executor = TerraformExecutor(
            working_directory=working_dir,
            var_files=["../config/int/int_config.tfvars"],
        )

        # Pass a plan file that does NOT exist
        result = executor.apply(plan_file=Path("tfplan-int-missing.tfplan"))

        assert result.exit_code == 1
        assert "not found" in result.stderr.lower()
        # subprocess.run must NOT have been called — no terraform command ran
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_apply_with_full_path_plan_file(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """apply() handles full (absolute) path plan files correctly.

        When cli.py passes the full plan file path instead of a bare filename,
        the executor resolves it to a relative name for the terraform command.
        """
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        working_dir = tmp_path / "terraform" / "modules"
        working_dir.mkdir(parents=True)

        plan_file = working_dir / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan")

        executor = TerraformExecutor(
            working_directory=working_dir,
            var_files=["../config/int/int_config.tfvars"],
        )

        # Pass full path (as _apply_with_plan now does)
        executor.apply(plan_file=plan_file)

        call_args = mock_run.call_args
        args = call_args[0][0]

        # The plan filename must appear in the command (relative to working_dir)
        assert plan_file.name in args
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


class TestVersion:
    """Tests for TerraformExecutor.version()."""

    @patch("subprocess.run")
    def test_version_parses_json_output(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """version() extracts terraform_version from JSON output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"terraform_version":"1.9.8","platform":"linux_amd64"}',
            stderr="",
        )
        assert executor.version() == "1.9.8"

    @patch("subprocess.run")
    def test_version_returns_unknown_on_failure(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """version() returns 'unknown' when terraform command fails."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        assert executor.version() == "unknown"

    @patch("subprocess.run")
    def test_version_returns_unknown_on_invalid_json(
        self, mock_run: MagicMock, executor: TerraformExecutor
    ) -> None:
        """version() returns 'unknown' on malformed JSON."""
        mock_run.return_value = MagicMock(returncode=0, stdout="not json", stderr="")
        assert executor.version() == "unknown"
