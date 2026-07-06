"""Tests for CLI module."""

import json
from pathlib import Path
from textwrap import dedent

import pytest
import typer
from typer.testing import CliRunner

from tf_branch_deploy.artifacts import params_hash_from_artifact_name
from tf_branch_deploy.cli import (
    ALLOWED_APPLY_CONFIG_ARG_FLAGS,
    ALLOWED_EXTRA_ARG_FLAGS,
    BLOCKED_EXTRA_ARG_FLAGS,
    DEFAULT_CONFIG_PATH,
    _ArgTokenizer,
    _apply_with_plan,
    _handle_apply,
    _handle_plan,
    _load_and_validate_config,
    _parse_extra_args,
    _strip_shell_quotes,
    _validate_config_args,
    _validate_extra_args,
    app,
    set_github_output,
)

runner = CliRunner()


def _save_plan_metadata(
    plan_file: Path,
    *,
    environment: str = "int",
    sha: str = "abc12345ff",
    extra_args: list[str] | None = None,
    plan_args: list[str] | None = None,
    var_files: list[str] | None = None,
    terraform_version: str = "1.9.8",
    checksum: str | None = None,
    params_hash: str = "no-args",
) -> None:
    """Create valid v0.2 plan metadata for apply tests."""
    from tf_branch_deploy.artifacts import PlanMetadata, calculate_checksum, save_plan_metadata

    save_plan_metadata(
        plan_file,
        PlanMetadata(
            environment=environment,
            sha=sha,
            checksum=checksum or calculate_checksum(plan_file),
            extra_args=extra_args or [],
            plan_args=plan_args or [],
            var_files=var_files or [],
            terraform_version=terraform_version,
            params_hash=params_hash,
            created_at="2025-01-15T10:00:00+00:00",
        ),
    )


class TestConstants:
    """Tests for CLI constants."""

    def test_default_config_path_is_path(self) -> None:
        assert isinstance(DEFAULT_CONFIG_PATH, Path)

    def test_default_config_path_value(self) -> None:
        assert str(DEFAULT_CONFIG_PATH) == ".tf-branch-deploy.yml"


class TestGithubOutput:
    """Tests for GitHub Actions output handling."""

    def test_outputs_use_multiline_file_command_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Output values are written as data, not single-line shell assignments."""
        output_file = tmp_path / "github-output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        set_github_output("failure_reason", "first line\nsecond line")
        text = output_file.read_text(encoding="utf-8")

        assert text.startswith("failure_reason<<TFBD_failure_reason_")
        assert "\nfirst line\nsecond line\n" in text
        assert "failure_reason=first line" not in text

    def test_single_line_outputs_also_use_multiline_format(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Keep one output-writing path for both trusted and untrusted values."""
        output_file = tmp_path / "github-output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        set_github_output("has_changes", "true")
        text = output_file.read_text(encoding="utf-8")

        assert text.startswith("has_changes<<TFBD_has_changes_")
        assert "\ntrue\n" in text
        assert text.count("has_changes=") == 0


class TestParseExtraArgs:
    """Tests for _parse_extra_args function."""

    def test_simple_args(self) -> None:
        result = _parse_extra_args("-refresh=false -parallelism=5")
        assert result == ["-refresh=false", "-parallelism=5"]

    def test_single_quoted_value(self) -> None:
        result = _parse_extra_args("-var='msg=hello world'")
        assert result == ["-var=msg=hello world"]

    def test_double_quoted_value(self) -> None:
        result = _parse_extra_args('-var="key=value"')
        assert result == ["-var=key=value"]

    def test_bracket_with_quotes(self) -> None:
        result = _parse_extra_args('-target=module.test["key"]')
        assert result == ['-target=module.test["key"]']

    def test_mixed_args(self) -> None:
        result = _parse_extra_args("-var='x=1' -target=module.foo -refresh=false")
        assert result == ["-var=x=1", "-target=module.foo", "-refresh=false"]

    def test_empty_string(self) -> None:
        result = _parse_extra_args("")
        assert result == []

    def test_spaces_in_value(self) -> None:
        """Test preserving spaces within quoted values."""
        result = _parse_extra_args("-var='message=hello world foo bar'")
        assert result == ["-var=message=hello world foo bar"]


class TestValidateExtraArgs:
    """Tests for _validate_extra_args function."""

    def test_allowed_flags_pass(self) -> None:
        """Allowed flags pass validation."""
        args = ["-target=module.base", "-refresh=false", "-parallelism=5"]
        result = _validate_extra_args(args)
        assert result == args

    def test_var_allowed(self) -> None:
        """The -var flag is allowed."""
        args = ["-var=key=value"]
        assert _validate_extra_args(args) == args

    def test_var_file_relative_path_allowed(self) -> None:
        """PR comment -var-file accepts relative paths inside the Terraform root."""
        args = ["-var-file=env/dev.tfvars", "-var-file", "./shared.tfvars"]
        assert _validate_extra_args(args) == args

    def test_var_file_missing_relative_path_inside_working_dir_allowed(
        self, tmp_path: Path
    ) -> None:
        """A repo-local var file path does not have to exist before Terraform reads it."""
        working_dir = tmp_path / "terraform"
        working_dir.mkdir()

        args = ["-var-file=env/dev.tfvars"]

        assert _validate_extra_args(args, working_dir) == args

    def test_var_file_symlink_directory_escape_blocked(self, tmp_path: Path) -> None:
        """PR comment -var-file must not escape through a symlinked directory."""
        working_dir = tmp_path / "terraform"
        outside_dir = tmp_path / "outside"
        working_dir.mkdir()
        outside_dir.mkdir()

        symlink_dir = working_dir / "linked"
        try:
            symlink_dir.symlink_to(outside_dir, target_is_directory=True)
        except OSError:
            pytest.skip("symlinks are not supported on this filesystem")

        with pytest.raises(typer.Exit):
            _validate_extra_args(["-var-file=linked/secret.tfvars"], working_dir)

    def test_var_file_symlink_file_escape_blocked(self, tmp_path: Path) -> None:
        """PR comment -var-file must not escape through a symlinked file."""
        working_dir = tmp_path / "terraform"
        outside_dir = tmp_path / "outside"
        working_dir.mkdir()
        outside_dir.mkdir()
        outside_file = outside_dir / "secret.tfvars"
        outside_file.write_text('token = "secret"\n', encoding="utf-8")

        symlink_file = working_dir / "secret.tfvars"
        try:
            symlink_file.symlink_to(outside_file)
        except OSError:
            pytest.skip("symlinks are not supported on this filesystem")

        with pytest.raises(typer.Exit):
            _validate_extra_args(["-var-file=secret.tfvars"], working_dir)

    @pytest.mark.parametrize(
        "arg",
        [
            "-var-file=/etc/passwd",
            r"-var-file=C:\secret.tfvars",
            r"-var-file=\\server\share\secret.tfvars",
            "-var-file=../secret.tfvars",
            "-var-file=env/../../secret.tfvars",
            "-var-file=~/secret.tfvars",
            "-var-file=",
        ],
    )
    def test_var_file_unsafe_paths_blocked(self, arg: str) -> None:
        """PR comment -var-file must not read outside the working directory."""
        with pytest.raises(typer.Exit):
            _validate_extra_args([arg])

    @pytest.mark.parametrize("path", ["/etc/passwd", "../secret.tfvars", "env\\..\\secret.tfvars"])
    def test_var_file_unsafe_split_paths_blocked(self, path: str) -> None:
        """Split -var-file values get the same path validation as inline values."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["-var-file", path])

    def test_split_value_flags_allowed(self) -> None:
        """Common Terraform flag value forms should match Terraform CLI behavior."""
        args = ["-var", "key=value", "-target", "module.database"]
        assert _validate_extra_args(args) == args

    def test_split_value_flag_requires_value(self) -> None:
        """Flags that require values should not swallow the next flag."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["-target", "-refresh=false"])

    def test_standalone_value_blocked(self) -> None:
        """Bare values are rejected so arguments stay tied to allowlisted flags."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["module.database"])

    def test_destroy_blocked(self) -> None:
        """The -destroy flag is blocked."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["-destroy"])

    def test_backend_config_blocked(self) -> None:
        """The -backend-config flag is blocked."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["-backend-config=key=value"])

    def test_state_blocked(self) -> None:
        """The -state flag is blocked."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["-state=/tmp/evil.tfstate"])

    def test_migrate_state_blocked(self) -> None:
        """The -migrate-state flag is blocked."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["-migrate-state"])

    def test_unknown_flag_blocked(self) -> None:
        """Unknown flags that aren't in the allowlist are blocked."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["-some-unknown-flag=value"])

    def test_mixed_valid_then_blocked_fails(self) -> None:
        """If any arg is blocked, the whole set fails."""
        with pytest.raises(typer.Exit):
            _validate_extra_args(["-target=module.base", "-destroy"])

    def test_empty_list_passes(self) -> None:
        """Empty args list passes validation."""
        assert _validate_extra_args([]) == []

    def test_all_allowed_flags_accepted(self) -> None:
        """All flags in ALLOWED_EXTRA_ARG_FLAGS pass validation."""
        args = [f"{flag}=test" for flag in sorted(ALLOWED_EXTRA_ARG_FLAGS)]
        result = _validate_extra_args(args)
        assert len(result) == len(ALLOWED_EXTRA_ARG_FLAGS)

    def test_all_blocked_flags_rejected(self) -> None:
        """All flags in BLOCKED_EXTRA_ARG_FLAGS are rejected."""
        for flag in BLOCKED_EXTRA_ARG_FLAGS:
            with pytest.raises(typer.Exit):
                _validate_extra_args([flag])


class TestValidateConfigArgs:
    """Tests for configured Terraform argument safety."""

    def test_plan_args_accept_targets(self) -> None:
        _validate_config_args(["-target=module.database"], [])

    def test_apply_args_accept_direct_apply_flags(self) -> None:
        args = [f"{flag}=test" for flag in sorted(ALLOWED_APPLY_CONFIG_ARG_FLAGS)]
        _validate_config_args([], args)

    def test_apply_args_reject_target(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_config_args([], ["-target=module.database"])

    def test_apply_args_reject_replace(self) -> None:
        with pytest.raises(typer.Exit):
            _validate_config_args([], ["-replace=aws_instance.app"])

    def test_config_args_do_not_use_pr_var_file_path_policy(self) -> None:
        """Trusted repo config may still use shared var files outside an env dir."""
        _validate_config_args(["-var-file=../shared/common.tfvars"], [])

    def test_apply_args_accept_split_var(self) -> None:
        _validate_config_args([], ["-var", "key=value"])


class TestPlanArtifactName:
    """Tests for extracting saved plan identity from workflow artifact names."""

    @pytest.mark.parametrize("params_hash", ["no-args", "a1b2c3d4"])
    def test_extracts_params_hash_from_valid_name(self, params_hash: str) -> None:
        artifact_name = f"tfplan-int-abc12345ff-{params_hash}-123456789-1"

        assert params_hash_from_artifact_name(artifact_name, "int", "abc12345ff") == params_hash

    @pytest.mark.parametrize(
        "artifact_name",
        [
            None,
            "",
            "tfplan-prod-abc12345ff-no-args-123456789-1",
            "tfplan-int-different-no-args-123456789-1",
            "tfplan-int-abc12345ff-123456789-1",
            "tfplan-int-abc12345ff-not-a-hash-123456789-1",
        ],
    )
    def test_returns_none_for_missing_or_untrusted_name(self, artifact_name: str | None) -> None:
        assert params_hash_from_artifact_name(artifact_name, "int", "abc12345ff") is None


class TestStripShellQuotes:
    """Tests for _strip_shell_quotes function."""

    def test_single_quotes(self) -> None:
        """Strip single quotes from value."""
        assert _strip_shell_quotes("-var='value'") == "-var=value"

    def test_double_quotes(self) -> None:
        """Strip double quotes from value."""
        assert _strip_shell_quotes('-var="value"') == "-var=value"

    def test_no_quotes(self) -> None:
        """Leave unquoted values unchanged."""
        assert _strip_shell_quotes("-var=value") == "-var=value"

    def test_no_equals(self) -> None:
        """Arguments without = are left unchanged."""
        assert _strip_shell_quotes("-help") == "-help"

    def test_preserve_internal_quotes(self) -> None:
        """Internal quotes in terraform targets are preserved."""
        assert _strip_shell_quotes('-target=module["key"]') == '-target=module["key"]'


class TestArgTokenizer:
    """Tests for _ArgTokenizer class."""

    def test_tokenize_simple(self) -> None:
        """Tokenize simple space-separated args."""
        tokenizer = _ArgTokenizer()
        result = tokenizer.tokenize("a b c")
        assert result == ["a", "b", "c"]

    def test_tokenize_preserves_quotes(self) -> None:
        """Tokenizer preserves quotes in output."""
        tokenizer = _ArgTokenizer()
        result = tokenizer.tokenize("-var='x=1'")
        assert result == ["-var='x=1'"]

    def test_tokenize_handles_brackets(self) -> None:
        """Tokenizer handles brackets in terraform args."""
        tokenizer = _ArgTokenizer()
        result = tokenizer.tokenize('-target=module["key"] -var=x')
        assert result == ['-target=module["key"]', "-var=x"]


class TestLoadAndValidateConfig:
    """Tests for _load_and_validate_config function."""

    def test_valid_config(self, tmp_path: Path) -> None:
        """Returns config and env_config for valid config."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            """
            default-environment: dev
            production-environments: [prod]
            environments:
              dev: {}
              prod: {}
            """
        )
        config, env_config = _load_and_validate_config(config_file, "dev")
        assert config is not None
        assert env_config is not None

    def test_missing_environment_exits(self, tmp_path: Path) -> None:
        """Exits with error for non-existent environment."""
        import pytest
        from click.exceptions import Exit

        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            """
            default-environment: dev
            production-environments: [prod]
            environments:
              dev: {}
              prod: {}
            """
        )
        with pytest.raises(Exit):
            _load_and_validate_config(config_file, "nonexistent")


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_config(self, tmp_path: Path) -> None:
        """Test validating a correct config file."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            dedent("""
            default-environment: dev
            production-environments:
              - prod
            environments:
              dev:
                working-directory: ./terraform/dev
              prod:
                working-directory: ./terraform/prod
        """)
        )

        result = runner.invoke(app, ["validate", "--config", str(config_file)])

        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    def test_validate_missing_config(self, tmp_path: Path) -> None:
        """Test error when config file doesn't exist."""
        result = runner.invoke(app, ["validate", "--config", str(tmp_path / "missing.yml")])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_validate_invalid_config(self, tmp_path: Path) -> None:
        """Test error for invalid config."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            dedent("""
            # Missing required fields
            environments:
              dev: {}
        """)
        )

        result = runner.invoke(app, ["validate", "--config", str(config_file)])

        assert result.exit_code == 1


class TestEnvironmentsCommand:
    """Tests for the environments command."""

    def test_list_environments(self, tmp_path: Path) -> None:
        """Test listing environments from config."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            dedent("""
            default-environment: dev
            production-environments: [prod]
            environments:
              dev: {}
              staging: {}
              prod: {}
        """)
        )

        result = runner.invoke(app, ["environments", "--config", str(config_file)])

        assert result.exit_code == 0
        # Should contain all environments
        assert "dev" in result.stdout
        assert "staging" in result.stdout
        assert "prod" in result.stdout


class TestSchemaCommand:
    """Tests for the schema command."""

    def test_outputs_valid_json(self) -> None:
        """Test that schema command outputs valid JSON."""
        result = runner.invoke(app, ["schema"])

        assert result.exit_code == 0
        # Output should be parseable JSON
        schema = json.loads(result.stdout)
        assert "properties" in schema


class TestGetConfigCommand:
    """Tests for get-config command."""

    def test_get_default_environment(self, tmp_path: Path) -> None:
        """Test getting default environment."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            "default-environment: dev\nproduction-environments: [prod]\nenvironments: {dev: {}, prod: {}}"
        )

        result = runner.invoke(
            app, ["get-config", "default-environment", "--config", str(config_file)]
        )

        assert result.exit_code == 0
        assert "dev" in result.stdout

    def test_get_production_environments(self, tmp_path: Path) -> None:
        """Test getting production environments."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            "default-environment: dev\nproduction-environments: [prod, stage]\nenvironments: {dev: {}, prod: {}, stage: {}}"
        )

        result = runner.invoke(
            app, ["get-config", "production-environments", "--config", str(config_file)]
        )

        assert result.exit_code == 0
        assert "prod,stage" in result.stdout

    def test_invalid_key(self, tmp_path: Path) -> None:
        """Test getting invalid key."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            "default-environment: dev\nproduction-environments: [prod]\nenvironments: {dev: {}, prod: {}}"
        )

        result = runner.invoke(app, ["get-config", "invalid-key", "--config", str(config_file)])

        assert result.exit_code == 1
        assert "Unsupported key" in result.stdout


class TestCompleteLifecycleCommand:
    """Tests for complete-lifecycle command."""

    def test_missing_env_vars(self) -> None:
        """Test error when required env vars are missing."""
        result = runner.invoke(app, ["complete-lifecycle", "--status", "success"])
        assert result.exit_code == 1
        assert "GH_REPO/GITHUB_REPOSITORY or GITHUB_TOKEN not set" in result.stdout

    def test_success(self, monkeypatch) -> None:
        """Test successful execution with mocked environment."""
        from unittest.mock import MagicMock, patch

        # Mock environment variables individually
        monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
        monkeypatch.setenv("GITHUB_TOKEN", "token")
        monkeypatch.setenv("TF_BD_DEPLOYMENT_ID", "123")
        monkeypatch.setenv("TF_BD_ENVIRONMENT", "dev")
        monkeypatch.setenv("TF_BD_COMMENT_ID", "456")
        monkeypatch.setenv("TF_BD_INITIAL_REACTION_ID", "789")
        monkeypatch.setenv("TF_BD_PR_NUMBER", "10")

        # Mock LifecycleManager
        with patch("tf_branch_deploy.lifecycle.LifecycleManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager_cls.return_value = mock_manager

            result = runner.invoke(app, ["complete-lifecycle", "--status", "success"])

            assert result.exit_code == 0
            assert "Lifecycle complete" in result.stdout

            # Verify manager calls
            mock_manager.update_deployment_status.assert_called_with("123", "success", "dev")
            mock_manager.remove_reaction.assert_called_with("456", "789")
            mock_manager.add_reaction.assert_called_with("456", "rocket")
            mock_manager.post_result_comment.assert_called()
            mock_manager.remove_non_sticky_lock.assert_called_with("dev")

    def test_failure_still_removes_non_sticky_lock(self, monkeypatch) -> None:
        """Failed Terraform runs should still release non-sticky deployment locks."""
        from unittest.mock import MagicMock, patch

        monkeypatch.setenv("GITHUB_REPOSITORY", "org/repo")
        monkeypatch.setenv("GITHUB_TOKEN", "token")
        monkeypatch.setenv("TF_BD_DEPLOYMENT_ID", "123")
        monkeypatch.setenv("TF_BD_ENVIRONMENT", "dev")
        monkeypatch.setenv("TF_BD_PR_NUMBER", "10")

        with patch("tf_branch_deploy.lifecycle.LifecycleManager") as mock_manager_cls:
            mock_manager = MagicMock()
            mock_manager_cls.return_value = mock_manager

            result = runner.invoke(
                app,
                [
                    "complete-lifecycle",
                    "--status",
                    "failure",
                    "--failure-reason",
                    "Terraform failed",
                ],
            )

        assert result.exit_code == 0
        mock_manager.update_deployment_status.assert_called_with("123", "failure", "dev")
        mock_manager.post_result_comment.assert_called()
        mock_manager.remove_non_sticky_lock.assert_called_with("dev")


class TestHandlePlan:
    """Tests for plan output and metadata handling."""

    def test_failed_plan_does_not_emit_saved_plan_outputs_or_metadata(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failed plan must not turn a stale plan file into a saved-plan artifact."""
        from unittest.mock import MagicMock

        from tf_branch_deploy.executor import PlanResult

        output_file = tmp_path / "github-output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))

        stale_plan = tmp_path / "tfplan-int-abc12345.tfplan"
        stale_plan.write_bytes(b"stale plan")

        mock_executor = MagicMock()
        mock_executor.plan.return_value = PlanResult(
            exit_code=1,
            stdout="",
            stderr="plan failed",
            command=["terraform", "plan"],
            has_changes=False,
            plan_file=stale_plan,
            checksum="not-a-real-checksum",
        )

        with pytest.raises(typer.Exit):
            _handle_plan(
                mock_executor,
                "int",
                "abc12345ff",
                plan_args=[],
                var_files=[],
                raw_extra_args="",
            )

        output_text = output_file.read_text(encoding="utf-8")
        assert "failure_reason" in output_text
        assert "plan_file" not in output_text
        assert "plan_checksum" not in output_text
        assert not stale_plan.with_suffix(".meta.json").exists()


class TestHandleApply:
    """Tests for _handle_apply — rollback priority and plan file resolution."""

    def test_rollback_takes_priority_over_stale_plan(self, tmp_path: Path) -> None:
        """Rollback must execute directly, even if a stale plan file exists.

        Regression: if plan_file.exists() is checked before is_rollback,
        a stale cached plan could be consumed instead of doing a fresh
        stable-branch apply.
        """
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform" / "modules"
        working_dir.mkdir(parents=True)

        # Create a stale plan file that should NOT be used
        stale_plan = working_dir / "tfplan-int-abc12345.tfplan"
        stale_plan.write_bytes(b"stale targeted plan")

        mock_executor = MagicMock()
        mock_executor.apply.return_value = MagicMock(success=True)

        env_vars = {
            "TF_BD_IS_ROLLBACK": "true",
        }

        with patch.dict("os.environ", env_vars):
            _handle_apply(mock_executor, "int", "abc12345ff", working_dir)

        # Executor.apply() must be called with NO plan_file (rollback path)
        mock_executor.apply.assert_called_once_with()

    def test_explicit_rollback_operation_takes_priority_without_env(self, tmp_path: Path) -> None:
        """CLI rollback operation should not depend on TF_BD_IS_ROLLBACK."""
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        stale_plan = working_dir / "tfplan-int-abc12345.tfplan"
        stale_plan.write_bytes(b"stale plan")

        mock_executor = MagicMock()
        mock_executor.apply.return_value = MagicMock(success=True)

        with patch.dict("os.environ", {}, clear=False):
            _handle_apply(
                mock_executor,
                "int",
                "abc12345ff",
                working_dir,
                is_rollback=True,
            )

        mock_executor.apply.assert_called_once_with()

    def test_plan_file_used_when_not_rollback(self, tmp_path: Path) -> None:
        """Normal apply uses the restored plan file when it exists."""
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform" / "modules"
        working_dir.mkdir(parents=True)

        # Create the expected plan file
        plan_file = working_dir / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan")
        _save_plan_metadata(plan_file)

        mock_executor = MagicMock()
        mock_executor.apply.return_value = MagicMock(success=True)
        mock_executor.version.return_value = "1.9.8"

        env_vars = {
            "TF_BD_IS_ROLLBACK": "false",
            "TF_BD_PLAN_ARTIFACT_NAME": "tfplan-int-abc12345ff-no-args-123-1",
        }

        with patch.dict("os.environ", env_vars):
            _handle_apply(mock_executor, "int", "abc12345ff", working_dir)

        # Executor.apply() must be called WITH plan_file
        call_args = mock_executor.apply.call_args
        assert call_args is not None
        assert "plan_file" in call_args.kwargs or len(call_args.args) > 0
        plan_arg = call_args.kwargs.get("plan_file", call_args.args[0] if call_args.args else None)
        assert plan_arg is not None
        assert "tfplan-int-abc12345.tfplan" in str(plan_arg)

    def test_apply_passes_filename_only_to_executor(self, tmp_path: Path) -> None:
        """_apply_with_plan passes only the filename to executor, not the full path.

        The executor resolves plan_file relative to its working_directory.
        Passing the full path (which includes working_directory) would cause
        path doubling: working_dir/working_dir/filename.
        """
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform" / "modules"
        working_dir.mkdir(parents=True)

        plan_file = working_dir / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan")
        _save_plan_metadata(plan_file)

        mock_executor = MagicMock()
        mock_executor.apply.return_value = MagicMock(success=True)
        mock_executor.version.return_value = "1.9.8"

        with patch.dict("os.environ", {}, clear=False):
            _apply_with_plan(
                mock_executor,
                plan_file,
                "int",
                "abc12345ff",
                expected_params_hash="no-args",
            )

        call_args = mock_executor.apply.call_args
        plan_arg = call_args.kwargs.get("plan_file")
        # Must be just the filename — executor resolves from working_directory
        assert plan_arg == Path(plan_file.name)
        assert str(plan_arg) == plan_file.name

    def test_handle_apply_no_path_doubling(self, tmp_path: Path) -> None:
        """Regression test: _handle_apply must not cause path doubling.

        When working_dir is 'terraform/modules' and plan file is at
        'terraform/modules/tfplan-int-abc12345.tfplan', the executor must
        receive just the filename, not 'terraform/modules/tfplan-int-abc12345.tfplan'
        (which would be resolved to 'terraform/modules/terraform/modules/...').
        """
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform" / "modules"
        working_dir.mkdir(parents=True)

        plan_file = working_dir / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan")
        _save_plan_metadata(plan_file)

        mock_executor = MagicMock()
        mock_executor.apply.return_value = MagicMock(success=True)
        mock_executor.working_directory = working_dir
        mock_executor.version.return_value = "1.9.8"

        env_vars = {
            "TF_BD_IS_ROLLBACK": "false",
            "TF_BD_PLAN_ARTIFACT_NAME": "tfplan-int-abc12345ff-no-args-123-1",
        }

        with patch.dict("os.environ", env_vars):
            _handle_apply(mock_executor, "int", "abc12345ff", working_dir)

        call_args = mock_executor.apply.call_args
        plan_arg = call_args.kwargs.get("plan_file", call_args.args[0] if call_args.args else None)
        # The executor receives just the filename — no path doubling possible
        assert str(plan_arg) == "tfplan-int-abc12345.tfplan"
        # Verify it does NOT contain the working_dir prefix
        assert "terraform/modules" not in str(plan_arg)

    def test_handle_apply_rejects_artifact_metadata_params_mismatch(self, tmp_path: Path) -> None:
        """Apply refuses a restored plan when artifact name and metadata disagree."""
        from click.exceptions import Exit as ClickExit
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()

        plan_file = working_dir / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan")
        _save_plan_metadata(plan_file, params_hash="a1b2c3d4")

        mock_executor = MagicMock()

        env_vars = {
            "TF_BD_IS_ROLLBACK": "false",
            "TF_BD_PLAN_ARTIFACT_NAME": "tfplan-int-abc12345ff-deadbeef-123-1",
        }

        with patch.dict("os.environ", env_vars):
            with pytest.raises(ClickExit):
                _handle_apply(mock_executor, "int", "abc12345ff", working_dir)

        mock_executor.apply.assert_not_called()

    def test_apply_rejects_extra_args(self, tmp_path: Path) -> None:
        """Normal apply must not accept fresh Terraform args from comments."""
        from click.exceptions import Exit as ClickExit
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        plan_file = working_dir / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan")
        _save_plan_metadata(plan_file)

        mock_executor = MagicMock()

        with patch.dict(
            "os.environ",
            {"TF_BD_IS_ROLLBACK": "false", "TF_BD_EXTRA_ARGS": "-target=module.database"},
        ):
            with pytest.raises(ClickExit):
                _handle_apply(mock_executor, "int", "abc12345ff", working_dir)

        mock_executor.apply.assert_not_called()

    def test_rollback_rejects_extra_args(self, tmp_path: Path) -> None:
        """Rollback is a stable-branch apply, not a target-only undo."""
        from click.exceptions import Exit as ClickExit
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        mock_executor = MagicMock()

        with patch.dict(
            "os.environ",
            {"TF_BD_IS_ROLLBACK": "true", "TF_BD_EXTRA_ARGS": "-target=module.database"},
        ):
            with (
                pytest.raises(ClickExit),
                patch("tf_branch_deploy.cli.set_github_output") as mock_output,
            ):
                _handle_apply(mock_executor, "int", "abc12345ff", working_dir)

        mock_executor.apply.assert_not_called()
        mock_output.assert_called_with(
            "failure_reason",
            (
                "Extra Terraform arguments are only supported on plan commands. "
                "Apply uses the saved plan. Rollback applies the stable branch directly; "
                "Terraform does not provide a deterministic target-only rollback."
            ),
        )


class TestApplyWithPlanIntegrity:
    """Tests for plan integrity verification in _apply_with_plan."""

    def test_checksum_verified_from_metadata_sidecar(self, tmp_path: Path) -> None:
        """Checksum verified successfully via metadata sidecar."""
        from unittest.mock import MagicMock, patch

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")
        _save_plan_metadata(
            plan_file,
            extra_args=["-target=module.base"],
            plan_args=["-target=module.base"],
        )

        mock_executor = MagicMock()
        mock_executor.apply.return_value = MagicMock(success=True)
        mock_executor.version.return_value = "1.9.8"

        with patch.dict("os.environ", {}, clear=False):
            _apply_with_plan(
                mock_executor,
                plan_file,
                "int",
                "abc12345ff",
                expected_params_hash="no-args",
            )

        # apply() must be called with just the filename (executor resolves from working_dir)
        mock_executor.apply.assert_called_once_with(plan_file=Path(plan_file.name))

    def test_apply_surfaces_saved_plan_args_and_hash(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Apply should show the saved plan identity before using it."""
        from unittest.mock import MagicMock, patch

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")
        _save_plan_metadata(
            plan_file,
            extra_args=["-target=module.base"],
            plan_args=["-target=module.base"],
            params_hash="a1b2c3d4",
        )

        mock_executor = MagicMock()
        mock_executor.apply.return_value = MagicMock(success=True)
        mock_executor.version.return_value = "1.9.8"

        with patch.dict("os.environ", {}, clear=False):
            _apply_with_plan(
                mock_executor,
                plan_file,
                "int",
                "abc12345ff",
                expected_params_hash="a1b2c3d4",
            )

        output = capsys.readouterr().out
        assert "Plan was created with args:" in output
        assert "-target=module.base" in output
        assert "Plan params hash: a1b2c3d4" in output

    def test_saved_plan_cache_identity_required(self, tmp_path: Path) -> None:
        """Apply must know which cache key restored the plan before using it."""
        from unittest.mock import MagicMock, patch

        from click.exceptions import Exit as ClickExit

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")
        _save_plan_metadata(plan_file)

        mock_executor = MagicMock()

        with patch.dict("os.environ", {}, clear=False):
            with pytest.raises(ClickExit):
                _apply_with_plan(mock_executor, plan_file, "int", "abc12345ff")

        mock_executor.apply.assert_not_called()

    def test_saved_plan_params_hash_mismatch_aborts(self, tmp_path: Path) -> None:
        """A restored cache entry cannot apply a plan with different PR args."""
        from unittest.mock import MagicMock, patch

        from click.exceptions import Exit as ClickExit

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")
        _save_plan_metadata(plan_file, params_hash="a1b2c3d4")

        mock_executor = MagicMock()

        with patch.dict("os.environ", {}, clear=False):
            with pytest.raises(ClickExit):
                _apply_with_plan(
                    mock_executor,
                    plan_file,
                    "int",
                    "abc12345ff",
                    expected_params_hash="deadbeef",
                )

        mock_executor.apply.assert_not_called()

    def test_checksum_mismatch_aborts(self, tmp_path: Path) -> None:
        """Checksum mismatch from metadata sidecar aborts with exit code 1."""
        from unittest.mock import MagicMock, patch

        from click.exceptions import Exit as ClickExit

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")

        _save_plan_metadata(
            plan_file,
            checksum="wrong_checksum_value",
        )

        mock_executor = MagicMock()
        mock_executor.version.return_value = "1.9.8"

        with patch.dict("os.environ", {}, clear=False):
            with pytest.raises(ClickExit):
                _apply_with_plan(
                    mock_executor,
                    plan_file,
                    "int",
                    "abc12345ff",
                    expected_params_hash="no-args",
                )

        # apply() must NOT be called
        mock_executor.apply.assert_not_called()

    def test_tf_version_mismatch_aborts(self, tmp_path: Path) -> None:
        """Terraform version mismatch aborts with exit code 1."""
        from unittest.mock import MagicMock, patch

        from click.exceptions import Exit as ClickExit

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")
        _save_plan_metadata(plan_file, terraform_version="1.8.0")

        mock_executor = MagicMock()
        mock_executor.version.return_value = "1.9.8"  # Different!

        with patch.dict("os.environ", {}, clear=False):
            with pytest.raises(ClickExit):
                _apply_with_plan(
                    mock_executor,
                    plan_file,
                    "int",
                    "abc12345ff",
                    expected_params_hash="no-args",
                )

        mock_executor.apply.assert_not_called()

    def test_missing_metadata_aborts(self, tmp_path: Path) -> None:
        """A saved plan without metadata is refused instead of applied."""
        from unittest.mock import MagicMock, patch

        from click.exceptions import Exit as ClickExit

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")

        mock_executor = MagicMock()

        with patch.dict("os.environ", {"TF_BD_PLAN_CHECKSUM": "legacy"}, clear=False):
            with pytest.raises(ClickExit):
                _apply_with_plan(
                    mock_executor,
                    plan_file,
                    "int",
                    "abc12345ff",
                    expected_params_hash="no-args",
                )

        mock_executor.apply.assert_not_called()

    def test_metadata_environment_mismatch_aborts(self, tmp_path: Path) -> None:
        """Apply cannot consume a plan created for a different environment."""
        from unittest.mock import MagicMock, patch

        from click.exceptions import Exit as ClickExit

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")
        _save_plan_metadata(plan_file, environment="prod")

        mock_executor = MagicMock()

        with patch.dict("os.environ", {}, clear=False):
            with pytest.raises(ClickExit):
                _apply_with_plan(
                    mock_executor,
                    plan_file,
                    "int",
                    "abc12345ff",
                    expected_params_hash="no-args",
                )

        mock_executor.apply.assert_not_called()

    def test_metadata_sha_mismatch_aborts(self, tmp_path: Path) -> None:
        """Apply cannot consume a plan created for a different commit."""
        from unittest.mock import MagicMock, patch

        from click.exceptions import Exit as ClickExit

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")
        _save_plan_metadata(plan_file, sha="different-sha")

        mock_executor = MagicMock()

        with patch.dict("os.environ", {}, clear=False):
            with pytest.raises(ClickExit):
                _apply_with_plan(
                    mock_executor,
                    plan_file,
                    "int",
                    "abc12345ff",
                    expected_params_hash="no-args",
                )

        mock_executor.apply.assert_not_called()

    def test_tf_version_unknown_skips_check(self, tmp_path: Path) -> None:
        """When TF version is 'unknown' (either side), skip version check."""
        from unittest.mock import MagicMock, patch

        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"valid plan content")
        _save_plan_metadata(plan_file, terraform_version="unknown")

        mock_executor = MagicMock()
        mock_executor.apply.return_value = MagicMock(success=True)
        mock_executor.version.return_value = "1.9.8"

        with patch.dict("os.environ", {}, clear=False):
            _apply_with_plan(
                mock_executor,
                plan_file,
                "int",
                "abc12345ff",
                expected_params_hash="no-args",
            )

        # Should proceed despite version mismatch (unknown is ignored)
        mock_executor.apply.assert_called_once()


class TestExecuteArgumentSemantics:
    """End-to-end CLI checks for plan/apply argument rules."""

    def _write_config(self, tmp_path: Path, root_extra: str = "") -> Path:
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_text = dedent(f"""
            default-environment: int
            production-environments: [prod]
            environments:
              int:
                working-directory: {tmp_path}
              prod: {{}}
            """)
        if root_extra:
            config_text += "\n" + dedent(root_extra)
        config_file.write_text(config_text)
        return config_file

    def test_invalid_operation_fails_before_terraform_init(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        config_file = self._write_config(tmp_path)

        with patch("tf_branch_deploy.executor.TerraformExecutor.init") as mock_init:
            result = runner.invoke(
                app,
                [
                    "execute",
                    "--environment",
                    "int",
                    "--operation",
                    "destroy",
                    "--sha",
                    "abc12345ff",
                    "--config",
                    str(config_file),
                ],
            )

        assert result.exit_code == 1
        mock_init.assert_not_called()

    def test_apply_extra_args_fail_before_terraform_init(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        config_file = self._write_config(tmp_path)

        with patch("tf_branch_deploy.executor.TerraformExecutor.init") as mock_init:
            result = runner.invoke(
                app,
                [
                    "execute",
                    "--environment",
                    "int",
                    "--operation",
                    "apply",
                    "--sha",
                    "abc12345ff",
                    "--config",
                    str(config_file),
                    "--extra-args",
                    "-target=module.database",
                ],
            )

        assert result.exit_code == 1
        mock_init.assert_not_called()

    def test_config_apply_target_fails_before_terraform_init(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        config_file = self._write_config(
            tmp_path,
            """
            defaults:
              apply-args:
                args:
                  - "-target=module.database"
            """,
        )

        with patch("tf_branch_deploy.executor.TerraformExecutor.init") as mock_init:
            result = runner.invoke(
                app,
                [
                    "execute",
                    "--environment",
                    "int",
                    "--operation",
                    "plan",
                    "--sha",
                    "abc12345ff",
                    "--config",
                    str(config_file),
                ],
            )

        assert result.exit_code == 1
        mock_init.assert_not_called()

    def test_plan_appends_config_and_comment_args_in_dry_run(self, tmp_path: Path) -> None:
        config_file = self._write_config(
            tmp_path,
            """
            defaults:
              plan-args:
                args:
                  - "-parallelism=20"
            """,
        )

        result = runner.invoke(
            app,
            [
                "execute",
                "--environment",
                "int",
                "--operation",
                "plan",
                "--sha",
                "abc12345ff",
                "--config",
                str(config_file),
                "--dry-run",
                "--extra-args",
                "-target=module.database",
            ],
        )

        assert result.exit_code == 0
        assert "terraform plan -parallelism=20 -target=module.database" in result.stdout

    def test_plan_dry_run_redacts_inline_var_values(self, tmp_path: Path) -> None:
        config_file = self._write_config(tmp_path)

        result = runner.invoke(
            app,
            [
                "execute",
                "--environment",
                "int",
                "--operation",
                "plan",
                "--sha",
                "abc12345ff",
                "--config",
                str(config_file),
                "--dry-run",
                "--extra-args",
                "-var=token=super-secret",
            ],
        )

        assert result.exit_code == 0
        assert "super-secret" not in result.stdout
        assert "-var=token=***" in result.stdout

    def test_plan_dry_run_redacts_split_var_values(self, tmp_path: Path) -> None:
        config_file = self._write_config(tmp_path)

        result = runner.invoke(
            app,
            [
                "execute",
                "--environment",
                "int",
                "--operation",
                "plan",
                "--sha",
                "abc12345ff",
                "--config",
                str(config_file),
                "--dry-run",
                "--extra-args",
                "-var token=super-secret",
            ],
        )

        assert result.exit_code == 0
        assert "super-secret" not in result.stdout
        assert "-var ***" in result.stdout

    def test_apply_dry_run_never_shows_apply_args_for_saved_plan(self, tmp_path: Path) -> None:
        config_file = self._write_config(
            tmp_path,
            """
            defaults:
              apply-args:
                args:
                  - "-parallelism=20"
            """,
        )

        result = runner.invoke(
            app,
            [
                "execute",
                "--environment",
                "int",
                "--operation",
                "apply",
                "--sha",
                "abc12345ff",
                "--config",
                str(config_file),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "terraform apply <saved plan file>" in result.stdout
        assert "-parallelism=20" not in result.stdout

    def test_rollback_dry_run_shows_direct_apply_inputs(self, tmp_path: Path) -> None:
        config_file = self._write_config(
            tmp_path,
            """
            defaults:
              var-files:
                paths:
                  - terraform.tfvars
              apply-args:
                args:
                  - "-parallelism=20"
            """,
        )

        result = runner.invoke(
            app,
            [
                "execute",
                "--environment",
                "int",
                "--operation",
                "rollback",
                "--sha",
                "abc12345ff",
                "--config",
                str(config_file),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "terraform apply -var-file terraform.tfvars -parallelism=20" in result.stdout


class TestRestorePlanCommand:
    """Tests for the restore-plan command (artifact-based plan restore)."""

    SHA = "abc12345ff0000000000000000000000000000ff"  # sha[:8] == abc12345

    def _write_config(self, tmp_path: Path, working_dir: Path) -> Path:
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            dedent(f"""
            default-environment: dev
            production-environments: [prod]
            environments:
              dev:
                working-directory: {working_dir}
              prod: {{}}
            """)
        )
        return config_file

    def _setup_env(self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch") -> Path:
        output_file = tmp_path / "github-output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(output_file))
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        return output_file

    def _candidate(self):
        from tf_branch_deploy.artifacts import PlanArtifactCandidate

        return PlanArtifactCandidate(
            id=7,
            name=f"tfplan-dev-{self.SHA}-no-args-123-1",
            created_at="2026-07-06T00:00:00Z",
            expired=False,
            size_in_bytes=42,
            repository_id=100,
            head_repository_id=100,
            workflow_run_id=555,
        )

    def _invoke(self, config_file: Path, working_dir: Path):
        return runner.invoke(
            app,
            [
                "restore-plan",
                "--environment",
                "dev",
                "--sha",
                self.SHA,
                "--config",
                str(config_file),
                "--working-dir",
                str(working_dir),
            ],
        )

    def test_restore_success_writes_artifact_name_output(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        config_file = self._write_config(tmp_path, working_dir)
        output_file = self._setup_env(tmp_path, monkeypatch)
        candidate = self._candidate()

        store = MagicMock()
        store.find_latest.return_value = candidate

        def fake_extract(cand, dest_dir, environment):
            plan = dest_dir / "tfplan-dev-abc12345.tfplan"
            meta = dest_dir / "tfplan-dev-abc12345.meta.json"
            plan.write_bytes(b"plan")
            meta.write_text("{}")
            return [plan, meta]

        store.download_and_extract.side_effect = fake_extract

        with patch("tf_branch_deploy.artifacts.PlanArtifactStore", return_value=store):
            result = self._invoke(config_file, working_dir)

        assert result.exit_code == 0
        store.find_latest.assert_called_once_with("dev", self.SHA)
        text = output_file.read_text(encoding="utf-8")
        assert "artifact_name<<" in text
        assert candidate.name in text
        assert "failure_reason" not in text

    def test_no_artifact_found_sets_actionable_failure_reason(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        config_file = self._write_config(tmp_path, working_dir)
        output_file = self._setup_env(tmp_path, monkeypatch)

        store = MagicMock()
        store.find_latest.return_value = None

        with patch("tf_branch_deploy.artifacts.PlanArtifactStore", return_value=store):
            result = self._invoke(config_file, working_dir)

        assert result.exit_code == 1
        text = output_file.read_text(encoding="utf-8")
        assert "failure_reason<<" in text
        assert "No saved plan artifact found" in text
        assert ".plan to dev" in text

    def test_listing_failure_mentions_actions_read_permission(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        from unittest.mock import MagicMock, patch

        from tf_branch_deploy.artifacts import PlanArtifactError

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        config_file = self._write_config(tmp_path, working_dir)
        output_file = self._setup_env(tmp_path, monkeypatch)

        store = MagicMock()
        store.find_latest.side_effect = PlanArtifactError("HTTP 403")

        with patch("tf_branch_deploy.artifacts.PlanArtifactStore", return_value=store):
            result = self._invoke(config_file, working_dir)

        assert result.exit_code == 1
        text = output_file.read_text(encoding="utf-8")
        assert "failure_reason<<" in text
        assert "actions: read" in text

    def test_download_failure_sets_failure_reason(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        from unittest.mock import MagicMock, patch

        from tf_branch_deploy.artifacts import PlanArtifactError

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        config_file = self._write_config(tmp_path, working_dir)
        output_file = self._setup_env(tmp_path, monkeypatch)

        store = MagicMock()
        store.find_latest.return_value = self._candidate()
        store.download_and_extract.side_effect = PlanArtifactError("zip corrupt")

        with patch("tf_branch_deploy.artifacts.PlanArtifactStore", return_value=store):
            result = self._invoke(config_file, working_dir)

        assert result.exit_code == 1
        text = output_file.read_text(encoding="utf-8")
        assert "Failed to download or extract the saved plan artifact" in text

    def test_artifact_missing_expected_plan_sets_failure_reason(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        from unittest.mock import MagicMock, patch

        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        config_file = self._write_config(tmp_path, working_dir)
        output_file = self._setup_env(tmp_path, monkeypatch)

        store = MagicMock()
        store.find_latest.return_value = self._candidate()
        store.download_and_extract.return_value = []

        with patch("tf_branch_deploy.artifacts.PlanArtifactStore", return_value=store):
            result = self._invoke(config_file, working_dir)

        assert result.exit_code == 1
        text = output_file.read_text(encoding="utf-8")
        assert "did not contain the" in text

    def test_missing_token_sets_failure_reason(
        self, tmp_path: Path, monkeypatch: "pytest.MonkeyPatch"
    ) -> None:
        working_dir = tmp_path / "terraform"
        working_dir.mkdir()
        config_file = self._write_config(tmp_path, working_dir)
        output_file = self._setup_env(tmp_path, monkeypatch)
        monkeypatch.delenv("GITHUB_TOKEN")

        result = self._invoke(config_file, working_dir)

        assert result.exit_code == 1
        text = output_file.read_text(encoding="utf-8")
        assert "failure_reason<<" in text
