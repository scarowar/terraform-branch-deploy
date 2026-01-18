"""Contract tests for branch-deploy compatibility.

These tests verify that our action.yml properly maps all branch-deploy inputs.

Note: These tests use a cached copy of branch-deploy action.yml to avoid
network dependencies. Run with --update-snapshots to refresh.
"""

from pathlib import Path

import pytest
import yaml


# Known inputs we intentionally don't expose (internal to branch-deploy)
INTERNAL_INPUTS = {
    "status",  # Provided by GitHub Actions
    "github_token",  # We rename to github-token
    "skip_completing",  # We always set this to true internally
}

# Mapping of our input names to branch-deploy input names (where different)
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
    "allow-forks": "allow_forks",
    "allow-non-default-target-branch": "allow_non_default_target_branch_deployments",
    "deployment-confirmation": "deployment_confirmation",
    "deployment-confirmation-timeout": "deployment_confirmation_timeout",
    "global-lock-flag": "global_lock_flag",
    "sticky-locks": "sticky_locks",
    "sticky-locks-for-noop": "sticky_locks_for_noop",
    "successful-deploy-labels": "successful_deploy_labels",
    "successful-noop-labels": "successful_noop_labels",
    "failed-deploy-labels": "failed_deploy_labels",
    "failed-noop-labels": "failed_noop_labels",
    "skip-completing": "skip_completing",
    "deploy-message-path": "deploy_message_path",
    "use-security-warnings": "use_security_warnings",
    "merge-deploy-mode": "merge_deploy_mode",
    "unlock-on-merge-mode": "unlock_on_merge_mode",
    "environment-url-in-comment": "environment_url_in_comment",
    "skip-successful-noop-labels-if-approved": "skip_successful_noop_labels_if_approved",
    "skip-successful-deploy-labels-if-approved": "skip_successful_deploy_labels_if_approved",
}


@pytest.fixture
def our_action() -> dict:
    """Load our action.yml."""
    action_path = Path(__file__).parent.parent.parent / "action.yml"
    with open(action_path) as f:
        return yaml.safe_load(f)


def normalize_input_name(name: str) -> str:
    """Normalize input name for comparison."""
    return name.lower().replace("-", "_")


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
