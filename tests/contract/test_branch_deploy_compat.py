"""Contract tests for branch-deploy compatibility.

These tests verify that our action.yml properly maps all branch-deploy inputs
and will FAIL if branch-deploy adds new inputs we don't expose.
"""

from pathlib import Path

import httpx
import pytest
import yaml


# Known inputs we intentionally don't expose (internal to branch-deploy)
INTERNAL_INPUTS = {
    "status",  # Provided by GitHub Actions
    "github_token",  # We rename to github-token
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
def branch_deploy_action() -> dict:
    """Fetch the latest branch-deploy action.yml."""
    resp = httpx.get(
        "https://raw.githubusercontent.com/github/branch-deploy/main/action.yml",
        timeout=30,
    )
    resp.raise_for_status()
    return yaml.safe_load(resp.text)


@pytest.fixture
def our_action() -> dict:
    """Load our action.yml."""
    action_path = Path(__file__).parent.parent.parent / "action.yml"
    with open(action_path) as f:
        return yaml.safe_load(f)


def normalize_input_name(name: str) -> str:
    """Normalize input name for comparison."""
    return name.lower().replace("-", "_")


class TestBranchDeployCompatibility:
    """Tests verifying compatibility with branch-deploy."""

    def test_all_branch_deploy_inputs_are_mapped(
        self, branch_deploy_action: dict, our_action: dict
    ) -> None:
        """Verify we expose all branch-deploy inputs."""
        bd_inputs = set(branch_deploy_action.get("inputs", {}).keys())
        bd_inputs -= INTERNAL_INPUTS

        our_inputs = set(our_action.get("inputs", {}).keys())

        # Build reverse mapping: branch-deploy name -> our name
        reverse_mapping = {v: k for k, v in INPUT_MAPPINGS.items()}

        # Check each branch-deploy input
        missing = []
        for bd_input in bd_inputs:
            # Check direct match or mapped name
            our_name = reverse_mapping.get(bd_input, bd_input)
            normalized = normalize_input_name(our_name)

            found = any(
                normalize_input_name(our_input) == normalized
                or normalize_input_name(our_input) == normalize_input_name(bd_input)
                for our_input in our_inputs
            )

            if not found:
                missing.append(bd_input)

        if missing:
            pytest.fail(
                f"branch-deploy has inputs we don't expose:\n"
                f"{missing}\n\n"
                f"Add these to action.yml inputs and INPUT_MAPPINGS in this test."
            )

    def test_branch_deploy_outputs_are_passed_through(
        self, branch_deploy_action: dict, our_action: dict
    ) -> None:
        """Verify we expose important branch-deploy outputs."""
        # Key outputs we must expose
        required_outputs = {
            "continue",
            "triggered",
            "environment",
            "sha",
            "noop",
            "actor",
            "params",
            "deployment_id",
        }

        our_outputs = set(our_action.get("outputs", {}).keys())
        our_outputs_normalized = {normalize_input_name(o) for o in our_outputs}

        missing = []
        for output in required_outputs:
            if normalize_input_name(output) not in our_outputs_normalized:
                missing.append(output)

        if missing:
            pytest.fail(f"Missing required outputs: {missing}")
