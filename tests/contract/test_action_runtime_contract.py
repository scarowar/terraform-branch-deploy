"""Regression tests for the composite action runtime contract."""

from pathlib import Path
from typing import Any

import pytest
import yaml


@pytest.fixture
def action() -> dict[str, Any]:
    """Load action.yml."""
    action_path = Path(__file__).parent.parent.parent / "action.yml"
    with open(action_path) as f:
        return yaml.safe_load(f)


def step_by_name(action: dict[str, Any], name: str) -> dict[str, Any]:
    """Return an action step by name."""
    for step in action["runs"]["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"Missing action step: {name}")


def step_by_id(action: dict[str, Any], step_id: str) -> dict[str, Any]:
    """Return an action step by id."""
    for step in action["runs"]["steps"]:
        if step.get("id") == step_id:
            return step
    raise AssertionError(f"Missing action step id: {step_id}")


class TestCompositeRuntimeContract:
    """Tests for behavior that only exists inside action.yml."""

    def test_install_step_recreates_venv_for_two_mode_jobs(self, action: dict[str, Any]) -> None:
        """The action is invoked twice in one job, so venv setup must be idempotent."""
        step = step_by_name(action, "Install tf-branch-deploy")
        script = step["run"]

        assert step["env"]["ACTION_PATH"] == "${{ github.action_path }}"
        assert step["env"]["TFBD_VENV"] == "${{ runner.temp }}/tf-bd-venv"
        assert 'uv venv --clear "${TFBD_VENV}"' in script
        assert 'UV_PROJECT_ENVIRONMENT="${TFBD_VENV}"' in script
        assert 'uv sync --frozen --no-dev --project "${ACTION_PATH}"' in script
        assert "uv pip install" not in script
        assert "GITHUB_PATH" not in script

        detect_step = step_by_name(action, "[Trigger] Detect Environments from Config")
        execute_step = step_by_id(action, "tf-execute")
        lifecycle_step = step_by_name(action, "[Execute] Complete Deployment Lifecycle")
        expected_bin = "${{ runner.temp }}/tf-bd-venv/bin/tf-branch-deploy"

        assert detect_step["env"]["TFBD_BIN"] == expected_bin
        assert execute_step["env"]["TFBD_BIN"] == expected_bin
        assert lifecycle_step["env"]["TFBD_BIN"] == expected_bin
        assert '"$TFBD_BIN" execute' in execute_step["run"]
        assert '"$TFBD_BIN" complete-lifecycle' in lifecycle_step["run"]

    def test_uv_bootstrap_is_internal_and_enterprise_aware(self, action: dict[str, Any]) -> None:
        """uv setup should not depend on caller repo config or GHES tokens."""
        check_step = step_by_name(action, "Check uv")
        setup_step = step_by_name(action, "Setup uv")
        check_script = check_step["run"]

        assert check_step["env"]["TFBD_UV_VERSION"] == "0.11.11"
        assert "command -v uv" in check_script
        assert "uv --version" in check_script
        assert "needs-setup=${needs_setup}" in check_script

        assert setup_step["if"] == "steps.check-uv.outputs.needs-setup == 'true'"
        assert setup_step["uses"] == ("astral-sh/setup-uv@08807647e7069bb48b6ef5acd8ec9567f424441b")
        assert setup_step["with"]["version"] == "0.11.11"
        assert setup_step["with"]["working-directory"] == "${{ github.action_path }}"
        assert "github.server_url == 'https://github.com'" in setup_step["with"]["github-token"]
        assert "inputs.github-token" in setup_step["with"]["github-token"]
        assert "|| ''" in setup_step["with"]["github-token"]

    def test_trigger_mode_exports_state_required_by_execute_mode(
        self, action: dict[str, Any]
    ) -> None:
        """Execute mode depends on these env vars surviving in the same job."""
        export_step = step_by_name(action, "[Trigger] Export State to GITHUB_ENV")
        validate_step = step_by_name(action, "[Execute] Validate State")
        export_script = export_step["run"]
        validate_script = validate_step["run"]

        required_exports = [
            "TF_BD_CONTINUE",
            "TF_BD_ENVIRONMENT",
            "TF_BD_OPERATION",
            "TF_BD_IS_ROLLBACK",
            "TF_BD_SHA",
            "TF_BD_REF",
            "TF_BD_ACTOR",
            "TF_BD_PR_NUMBER",
            "TF_BD_PARAMS",
            "TF_BD_DEPLOYMENT_ID",
            "TF_BD_COMMENT_ID",
            "TF_BD_INITIAL_REACTION_ID",
            "TF_BD_NOOP",
            "TF_BD_TYPE",
        ]

        for env_name in required_exports:
            assert f'write_env "{env_name}"' in export_script

        assert '>> "$GITHUB_ENV"' in export_script
        assert 'echo "TF_BD_PARAMS=' not in export_script
        assert 'echo "TF_BD_EXTRA_ARGS=' not in export_script

        for env_name in ["TF_BD_ENVIRONMENT", "TF_BD_OPERATION", "TF_BD_SHA"]:
            assert env_name in validate_script

    def test_action_outputs_use_multiline_file_command_format(self, action: dict[str, Any]) -> None:
        """Branch Deploy and config values can be PR controlled, so outputs must be data-only."""
        detect_script = step_by_name(action, "[Trigger] Detect Environments from Config")["run"]
        derive_script = step_by_id(action, "derive-operation")["run"]

        for script in [detect_script, derive_script]:
            assert '>> "$GITHUB_OUTPUT"' in script
            assert "write_output()" in script

        assert 'echo "targets=' not in detect_script
        assert 'echo "default=' not in detect_script
        assert 'echo "production=' not in detect_script
        assert 'echo "operation=' not in derive_script
        assert 'echo "is_rollback=' not in derive_script

    def test_operation_derivation_keeps_plan_before_rollback(self, action: dict[str, Any]) -> None:
        """Plan detection must win before ref-based rollback detection."""
        step = step_by_id(action, "derive-operation")
        script = step["run"]

        noop_check = script.index('if [[ "$BD_NOOP" == "true" ]]')
        rollback_check = script.index('elif [[ "$BD_REF" == "$STABLE_BRANCH" ]]')

        assert noop_check < rollback_check
        assert 'OPERATION="plan"' in script
        assert 'OPERATION="rollback"' in script
        assert 'OPERATION="apply"' in script

    def test_trigger_config_detection_fails_closed(self, action: dict[str, Any]) -> None:
        """Trigger mode must not silently deploy to production when config is invalid."""
        step = step_by_name(action, "[Trigger] Detect Environments from Config")
        script = step["run"]

        assert "set -euo pipefail" in script
        assert "not found. Set config-path or environment-targets" in script
        assert '|| echo "production"' not in script
        assert 'targets="production"' not in script
        assert 'default="production"' not in script

    def test_terraform_tooling_is_execute_mode_only_and_skips_matching_tool(
        self, action: dict[str, Any]
    ) -> None:
        """Trigger mode should not require Terraform, and execute mode should reuse matches."""
        check_step = step_by_name(action, "Check Terraform")
        terraform_step = step_by_name(action, "Setup Terraform")
        check_script = check_step["run"]

        assert check_step["if"] == "inputs.mode == 'execute'"
        assert "command -v terraform" in check_script
        assert "terraform version -json" in check_script
        assert "INPUT_TERRAFORM_VERSION" in check_script
        assert (
            terraform_step["if"]
            == "inputs.mode == 'execute' && steps.check-terraform.outputs.needs-setup == 'true'"
        )

    def test_tfcmt_setup_reuses_preinstalled_tool_and_installs_to_runner_temp(
        self, action: dict[str, Any]
    ) -> None:
        """tfcmt should be optional bootstrap tooling, not a system mutation."""
        tfcmt_step = step_by_name(action, "Setup tfcmt")
        script = tfcmt_step["run"]

        assert tfcmt_step["if"] == "inputs.mode == 'execute'"
        assert tfcmt_step["env"]["TFBD_TOOL_DIR"] == "${{ runner.temp }}/tfbd-tools/bin"
        assert tfcmt_step["env"]["TFCMT_ARCHIVE"] == "${{ runner.temp }}/tfcmt.tar.gz"
        assert "command -v tfcmt" in script
        assert "curl --fail --silent --show-error --location --retry 3" in script
        assert "sha256sum -c --strict -" in script
        assert 'tar xz -C "${TFBD_TOOL_DIR}" tfcmt' in script
        assert "GITHUB_PATH" not in script
        assert "/usr/local/bin" not in script
        assert "Terraform will run without tfcmt PR comments" in script

        execute_step = step_by_id(action, "tf-execute")
        assert execute_step["env"]["TFBD_TOOL_DIR"] == "${{ runner.temp }}/tfbd-tools/bin"
        assert 'export PATH="${TFBD_TOOL_DIR}:${PATH}"' in execute_step["run"]

    def test_execute_mode_cache_restore_and_save_are_environment_and_sha_scoped(
        self, action: dict[str, Any]
    ) -> None:
        """A plan from another environment or SHA must not be restored."""
        restore_step = step_by_name(action, "[Execute] Restore Cached Plan")
        save_step = step_by_name(action, "[Execute] Cache Plan File")

        assert restore_step["uses"].startswith("actions/cache/restore@")
        assert restore_step["if"] == "inputs.mode == 'execute' && env.TF_BD_OPERATION == 'apply'"
        restore_paths = restore_step["with"]["path"].splitlines()
        assert "**/tfplan-${{ env.TF_BD_ENVIRONMENT }}-*.tfplan" in restore_paths
        assert "**/tfplan-${{ env.TF_BD_ENVIRONMENT }}-*.meta.json" in restore_paths
        assert (
            restore_step["with"]["key"]
            == "tfplan-${{ env.TF_BD_ENVIRONMENT }}-${{ env.TF_BD_SHA }}-${{ github.run_id }}-${{ github.run_attempt }}"
        )
        assert (
            "tfplan-${{ env.TF_BD_ENVIRONMENT }}-${{ env.TF_BD_SHA }}-"
            in restore_step["with"]["restore-keys"]
        )

        assert save_step["uses"].startswith("actions/cache@")
        assert save_step["if"] == "inputs.mode == 'execute' && env.TF_BD_OPERATION == 'plan'"
        save_paths = save_step["with"]["path"].splitlines()
        assert save_paths == restore_paths
        assert save_step["with"]["key"] == restore_step["with"]["key"]

    def test_lifecycle_completion_runs_on_success_and_failure_with_ghe_context(
        self, action: dict[str, Any]
    ) -> None:
        """Lifecycle completion must run even when terraform fails."""
        step = step_by_name(action, "[Execute] Complete Deployment Lifecycle")

        assert step["if"] == "inputs.mode == 'execute' && always()"
        assert step["env"]["GITHUB_SERVER_URL"] == "${{ github.server_url }}"
        assert step["env"]["GH_REPO"] == "${{ github.repository }}"
        assert step["env"]["STATUS"] == "${{ steps.tf-execute.outcome }}"
        assert step["env"]["FAILURE_REASON"] == "${{ steps.tf-execute.outputs.failure_reason }}"

    def test_execute_mode_passes_pr_comment_params_without_shell_expansion(
        self, action: dict[str, Any]
    ) -> None:
        """Extra Terraform args are parsed by Python, not interpolated into a shell command."""
        step = step_by_id(action, "tf-execute")
        script = step["run"]

        assert step["env"]["TF_BD_EXTRA_ARGS"] == "${{ env.TF_BD_PARAMS }}"
        assert "TF_BD_EXTRA_ARGS: ${{ env.TF_BD_PARAMS }}" not in script
        assert "--extra-args" not in script

    def test_execute_mode_does_not_expose_github_token_as_provider_env(
        self, action: dict[str, Any]
    ) -> None:
        """The deployment token must not be exported as GITHUB_TOKEN during Terraform."""
        execute_step = step_by_id(action, "tf-execute")
        lifecycle_step = step_by_name(action, "[Execute] Complete Deployment Lifecycle")

        assert "GITHUB_TOKEN" not in execute_step["env"]
        assert execute_step["env"]["TFBD_GITHUB_TOKEN"] == "${{ inputs.github-token }}"
        assert lifecycle_step["env"]["GITHUB_TOKEN"] == "${{ inputs.github-token }}"

    def test_shell_steps_do_not_interpolate_action_inputs_directly(
        self, action: dict[str, Any]
    ) -> None:
        """Action inputs are passed through env so shell parses data, not expressions."""
        for step in action["runs"]["steps"]:
            if "run" in step:
                assert "${{ inputs." not in step["run"], step.get("name", step.get("id"))
