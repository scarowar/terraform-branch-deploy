"""Contract tests for branch-deploy compatibility.

These tests verify that our action.yml properly maps all branch-deploy inputs.

Note: These tests use a cached copy of branch-deploy action.yml to avoid
network dependencies. Run with --update-snapshots to refresh.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml


BRANCH_DEPLOY_VERSION = "v11.1.2"
BRANCH_DEPLOY_SHA = "fded0351b6b79f854b335c11b3d93063461dd288"

# Branch Deploy inputs that Terraform Branch Deploy controls instead of exposing.
CONTROLLED_UPSTREAM_INPUTS = {
    "status",  # Branch Deploy post state; bypassed by skip_completing.
    "environment",  # Derived from .tf-branch-deploy.yml or environment-targets.
    "skip_completing",  # Always true; execute mode completes lifecycle.
    "allow_forks",  # Hard-disabled until fork-aware checkout is implemented.
}

# Branch Deploy inputs intentionally not supported in v0.2.0. These all belong
# to completion behavior bypassed by skip_completing or alternate workflow modes.
UNSUPPORTED_UPSTREAM_INPUTS = {
    "environment_url_in_comment",
    "merge_deploy_mode",
    "unlock_on_merge_mode",
    "deploy_message_path",
    "successful_deploy_labels",
    "successful_noop_labels",
    "failed_deploy_labels",
    "failed_noop_labels",
    "skip_successful_noop_labels_if_approved",
    "skip_successful_deploy_labels_if_approved",
}

TERRAFORM_NATIVE_INPUTS = {
    "mode",
    "config-path",
    "terraform-version",
    "uv-version",
    "dry-run",
}

# Mapping of public Terraform Branch Deploy inputs to supported Branch Deploy inputs.
INPUT_MAPPINGS = {
    "github-token": "github_token",
    "noop-trigger": "noop_trigger",
    "lock-trigger": "lock_trigger",
    "unlock-trigger": "unlock_trigger",
    "help-trigger": "help_trigger",
    "lock-info-alias": "lock_info_alias",
    "param-separator": "param_separator",
    "environment-targets": "environment_targets",
    "production-environments": "production_environments",
    "environment-urls": "environment_urls",
    "draft-permitted-targets": "draft_permitted_targets",
    "stable-branch": "stable_branch",
    "update-branch": "update_branch",
    "outdated-mode": "outdated_mode",
    "allow-sha-deployments": "allow_sha_deployments",
    "enforced-deployment-order": "enforced_deployment_order",
    "ignored-checks": "ignored_checks",
    "skip-ci": "skip_ci",
    "skip-reviews": "skip_reviews",
    "required-contexts": "required_contexts",
    "admins-pat": "admins_pat",
    "commit-verification": "commit_verification",
    "disable-naked-commands": "disable_naked_commands",
    "allow-non-default-target-branch": "allow_non_default_target_branch_deployments",
    "deployment-confirmation": "deployment_confirmation",
    "deployment-confirmation-timeout": "deployment_confirmation_timeout",
    "global-lock-flag": "global_lock_flag",
    "sticky-locks": "sticky_locks",
    "sticky-locks-for-noop": "sticky_locks_for_noop",
    "use-security-warnings": "use_security_warnings",
}

DERIVED_BRANCH_DEPLOY_INPUTS = {
    "environment": "${{ steps.detect-envs.outputs.default }}",
    "environment_targets": "${{ steps.detect-envs.outputs.targets }}",
    "production_environments": "${{ steps.detect-envs.outputs.production }}",
}

DIRECT_PASSTHROUGH_INPUTS = set(INPUT_MAPPINGS) - {
    "environment-targets",
    "production-environments",
}


@pytest.fixture
def our_action() -> dict[str, Any]:
    """Load our action.yml."""
    action_path = Path(__file__).parent.parent.parent / "action.yml"
    with open(action_path) as f:
        return yaml.safe_load(f)


@pytest.fixture
def branch_deploy_action() -> dict[str, Any]:
    """Load the pinned branch-deploy input snapshot."""
    fixture_path = (
        Path(__file__).parent.parent
        / "fixtures"
        / f"branch-deploy-{BRANCH_DEPLOY_VERSION}-inputs.yml"
    )
    with open(fixture_path) as f:
        return yaml.safe_load(f)


def normalize_input_name(name: str) -> str:
    """Normalize input name for comparison."""
    return name.lower().replace("-", "_")


def kebab_input_name(name: str) -> str:
    """Convert a branch-deploy input name to our public input naming style."""
    return name.lower().replace("_", "-")


def branch_deploy_step(action: dict[str, Any]) -> dict[str, Any]:
    """Return the embedded Branch Deploy step."""
    for step in action["runs"]["steps"]:
        if step.get("id") == "branch-deploy":
            return step
    raise AssertionError("Missing branch-deploy step")


class TestActionYmlValidity:
    """Tests verifying our action.yml is valid."""

    def test_action_has_required_fields(self, our_action: dict) -> None:
        """Verify action.yml has required fields."""
        assert "name" in our_action
        assert "description" in our_action
        assert "inputs" in our_action
        assert "runs" in our_action

    def test_action_has_essential_inputs(self, our_action: dict) -> None:
        """Verify we have essential inputs."""
        inputs = our_action.get("inputs", {})

        essential = ["github-token", "mode", "config-path"]
        for input_name in essential:
            assert input_name in inputs, f"Missing essential input: {input_name}"

    def test_action_has_essential_outputs(self, our_action: dict) -> None:
        """Verify we expose essential outputs."""
        outputs = our_action.get("outputs", {})

        essential = [
            "continue",
            "environment",
            "sha",
            "noop",
            "working-directory",
            "is-production",
        ]
        for output_name in essential:
            assert output_name in outputs, f"Missing essential output: {output_name}"

    def test_mode_input_has_valid_options(self, our_action: dict) -> None:
        """Verify mode input documents valid options."""
        mode_input = our_action["inputs"].get("mode", {})
        description = mode_input.get("description", "")

        # v0.2.0: trigger/execute modes (dispatch removed)
        assert "trigger" in description.lower() or "execute" in description.lower()

    def test_github_token_is_required(self, our_action: dict) -> None:
        """Verify github-token is marked as required."""
        github_token = our_action["inputs"].get("github-token", {})

        assert github_token.get("required") is True

    def test_branch_deploy_is_pinned_to_expected_sha(self, our_action: dict[str, Any]) -> None:
        """The embedded branch-deploy version is part of our release contract."""
        step = branch_deploy_step(our_action)

        assert step["uses"] == f"github/branch-deploy@{BRANCH_DEPLOY_SHA}"

    def test_branch_deploy_inputs_are_exhaustively_classified(
        self, our_action: dict[str, Any], branch_deploy_action: dict[str, Any]
    ) -> None:
        """Every upstream input must be supported, controlled, or unsupported by design."""
        upstream_inputs = set(branch_deploy_action["inputs"])
        public_branch_deploy_inputs = {
            INPUT_MAPPINGS.get(input_name, normalize_input_name(input_name))
            for input_name in our_action["inputs"]
            if input_name not in TERRAFORM_NATIVE_INPUTS
        }
        classified_inputs = (
            public_branch_deploy_inputs
            | CONTROLLED_UPSTREAM_INPUTS
            | UNSUPPORTED_UPSTREAM_INPUTS
        )

        assert upstream_inputs == classified_inputs

    def test_supported_public_inputs_are_declared(self, our_action: dict[str, Any]) -> None:
        """Mapped pass-through inputs must remain part of the public action API."""
        public_inputs = set(our_action["inputs"])

        assert set(INPUT_MAPPINGS) <= public_inputs
        assert TERRAFORM_NATIVE_INPUTS <= public_inputs

    def test_direct_branch_deploy_inputs_are_wired(self, our_action: dict[str, Any]) -> None:
        """Supported direct pass-through inputs must reach Branch Deploy."""
        branch_deploy_with = branch_deploy_step(our_action)["with"]

        for public_name in DIRECT_PASSTHROUGH_INPUTS:
            upstream_name = INPUT_MAPPINGS[public_name]
            assert branch_deploy_with[upstream_name] == f"${{{{ inputs.{public_name} }}}}"

    def test_environment_inputs_are_derived_before_branch_deploy(
        self, our_action: dict[str, Any]
    ) -> None:
        """Environment inputs are normalized from config before Branch Deploy sees them."""
        branch_deploy_with = branch_deploy_step(our_action)["with"]

        for upstream_name, expected_value in DERIVED_BRANCH_DEPLOY_INPUTS.items():
            assert branch_deploy_with[upstream_name] == expected_value

    def test_fork_deployments_are_hard_disabled(self, our_action: dict[str, Any]) -> None:
        """Forks require explicit fork-aware checkout support before being exposed."""
        public_inputs = set(our_action["inputs"])
        branch_deploy_with = branch_deploy_step(our_action)["with"]

        assert "allow-forks" not in public_inputs
        assert branch_deploy_with["allow_forks"] == "false"

    def test_unsupported_branch_deploy_inputs_are_not_public_or_wired(
        self, our_action: dict[str, Any]
    ) -> None:
        """Completion-only and alternate-mode inputs must not be silent no-ops."""
        public_inputs = set(our_action["inputs"])
        branch_deploy_with = branch_deploy_step(our_action)["with"]

        for upstream_name in UNSUPPORTED_UPSTREAM_INPUTS:
            assert kebab_input_name(upstream_name) not in public_inputs
            assert upstream_name not in branch_deploy_with
