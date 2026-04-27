"""Unit tests for the Terraform executor module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tf_branch_deploy.executor import (
    CommandResult,
    PlanResult,
    TerraformExecutor,
    _redact_args,
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
    def test_plan_resolves_relative_out_file_against_working_directory(
        self, mock_run: MagicMock, tmp_path: Path
    ) -> None:
        """plan() resolves relative out_file against working_directory.

        Regression test: when working_directory != CWD, a relative out_file
        must be resolved against working_directory so checksum calculation
        and plan_file return work correctly.
        """
        working_dir = tmp_path / "terraform" / "modules"
        working_dir.mkdir(parents=True)

        plan_name = "tfplan-int-abc12345.tfplan"
        plan_content = b"terraform plan binary"

        # Simulate terraform writing the plan file inside working_directory
        (working_dir / plan_name).write_bytes(plan_content)

        mock_run.return_value = MagicMock(returncode=2, stdout="", stderr="")

        executor = TerraformExecutor(
            working_directory=working_dir,
            var_files=["../config/int/int_config.tfvars"],
        )

        result = executor.plan(out_file=Path(plan_name))

        # plan_file must be set (resolved to working_directory)
        assert result.plan_file is not None
        assert result.plan_file.exists()
        # checksum must be calculated
        assert result.checksum is not None

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


class TestRedactArgs:
    """Tests for _redact_args log redaction."""

    def test_no_vars_unchanged(self) -> None:
        """Args without -var= are unchanged."""
        args = ["terraform", "plan", "-target=module.base"]
        assert _redact_args(args) == "terraform plan -target=module.base"

    def test_var_value_redacted(self) -> None:
        """The value part of -var=key=value is replaced with ***."""
        args = ["terraform", "plan", "-var=password=s3cr3t"]
        assert _redact_args(args) == "terraform plan -var=password=***"

    def test_multiple_vars_redacted(self) -> None:
        """Multiple -var= args are all redacted."""
        args = ["terraform", "plan", "-var=a=1", "-var=b=2"]
        assert _redact_args(args) == "terraform plan -var=a=*** -var=b=***"

    def test_var_file_not_redacted(self) -> None:
        """-var-file= is NOT the same as -var= and should not be redacted."""
        args = ["terraform", "plan", "-var-file=vars.tfvars"]
        assert _redact_args(args) == "terraform plan -var-file=vars.tfvars"

    def test_mixed_args(self) -> None:
        """Mix of -var, -target, and plain args."""
        args = ["terraform", "apply", "-var=token=abc123", "-target=module.foo"]
        result = _redact_args(args)
        assert "-var=token=***" in result
        assert "-target=module.foo" in result

    def test_var_with_spaces_fully_redacted(self) -> None:
        """Value containing spaces in a single token is fully redacted."""
        args = ["terraform", "plan", "-var=msg=hello world"]
        assert _redact_args(args) == "terraform plan -var=msg=***"

    def test_two_token_var_redacted(self) -> None:
        """-var key=value (two tokens) redacts the value token."""
        args = ["terraform", "plan", "-var", "password=s3cr3t"]
        assert _redact_args(args) == "terraform plan -var ***"

    def test_two_token_var_at_end(self) -> None:
        """-var at end of args (no value following) is left as-is."""
        args = ["terraform", "plan", "-var"]
        assert _redact_args(args) == "terraform plan -var"


class TestTimeout:
    """Tests for subprocess timeout handling."""

    def test_executor_default_timeout(self, tmp_path: Path) -> None:
        """Executor has a default timeout of 3600s."""
        executor = TerraformExecutor(working_directory=tmp_path)
        assert executor.timeout == 3600

    def test_executor_custom_timeout(self, tmp_path: Path) -> None:
        """Executor accepts a custom timeout."""
        executor = TerraformExecutor(working_directory=tmp_path, timeout=600)
        assert executor.timeout == 600

    @patch("tf_branch_deploy.executor.subprocess.run")
    def test_timeout_returns_exit_124(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """Timeout produces exit code 124 and descriptive stderr."""
        import subprocess as sp

        mock_run.side_effect = sp.TimeoutExpired(cmd=["terraform", "plan"], timeout=60)
        executor = TerraformExecutor(working_directory=tmp_path, timeout=60, dry_run=False)
        result = executor._run_command(["terraform", "plan"])
        assert result.exit_code == 124
        assert "timed out" in result.stderr
        assert not result.success

    @patch("tf_branch_deploy.executor.subprocess.run")
    def test_timeout_passed_to_subprocess(self, mock_run: MagicMock, tmp_path: Path) -> None:
        """The timeout value is passed to subprocess.run."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        executor = TerraformExecutor(working_directory=tmp_path, timeout=900, dry_run=False)
        executor._run_command(["terraform", "version"])
        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 900
