"""Security contracts for GitHub Actions workflows."""

from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).parent.parent.parent
WORKFLOW_FILES = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
ACTION_FILES = [REPO_ROOT / "action.yml"]
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
E2E_DISPATCH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "e2e-dispatch.yml"
ACTION_REF_RE = re.compile(r"@[0-9a-f]{40}$")


def _uses_references(path: Path) -> list[tuple[int, str]]:
    """Return `uses:` values from a workflow or action file."""
    refs: list[tuple[int, str]] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped.startswith("uses: "):
            continue
        value = stripped.removeprefix("uses: ").split("#", 1)[0].strip()
        refs.append((index, value))
    return refs


def test_privileged_pull_request_target_is_not_used() -> None:
    """IssueOps deployments must not use the privileged pull_request_target trigger."""
    for path in WORKFLOW_FILES:
        assert "pull_request_target" not in path.read_text(encoding="utf-8"), path


def test_repository_workflows_do_not_grant_broad_write_permissions() -> None:
    """Repository automation should stay least-privilege by default."""
    for path in WORKFLOW_FILES:
        text = path.read_text(encoding="utf-8")
        assert "write-all" not in text, path
        assert "contents: write" not in text, path


def test_actions_are_pinned_to_full_commit_sha() -> None:
    """Runtime workflows and the composite action should not depend on mutable tags."""
    for path in [*WORKFLOW_FILES, *ACTION_FILES]:
        for line_number, action_ref in _uses_references(path):
            if action_ref.startswith("./"):
                continue
            assert ACTION_REF_RE.search(action_ref), f"{path}:{line_number} uses {action_ref}"


def test_jobs_start_with_step_security_harden_runner() -> None:
    """Every workflow job should begin with Step Security runtime monitoring."""
    for path in WORKFLOW_FILES:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in workflow.get("jobs", {}).items():
            steps = job.get("steps", [])
            if not steps:
                continue
            first_step_uses = steps[0].get("uses", "")
            assert first_step_uses.startswith("step-security/harden-runner@"), (
                f"{path}:{job_name} does not start with Harden-Runner"
            )


def test_pre_commit_ci_is_configured_for_cloud_hygiene() -> None:
    """pre-commit.ci should run fast hygiene while CI owns heavyweight security gates."""
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text(encoding="utf-8"))
    ci_config = config.get("ci", {})

    assert ci_config["autoupdate_schedule"] == "weekly"
    assert ci_config["autofix_commit_msg"] == "style: apply pre-commit fixes"
    assert ci_config["autoupdate_commit_msg"] == "chore: update pre-commit hooks"
    assert {
        "pip-audit",
        "semgrep",
        "zizmor",
        "gitleaks",
        "actionlint",
    } <= set(ci_config["skip"])


def test_dependency_review_blocks_low_severity_and_above() -> None:
    """Dependency Review should fail on every vulnerability severity."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "dependency-review.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["dependency-review"]["steps"]
    dependency_review = next(
        step for step in steps if "dependency-review-action" in step.get("uses", "")
    )

    assert dependency_review["with"]["fail-on-severity"] == "low"


def test_security_workflow_runs_zero_finding_gates() -> None:
    """The security workflow should run deterministic scanners without severity filtering."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "security.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["deterministic-security"]["steps"]
    run_commands = "\n".join(step.get("run", "") for step in steps)

    assert "uv run pip-audit --strict" in run_commands
    assert "uv run bandit -r src" in run_commands
    assert "uv run zizmor --offline ." in run_commands
    assert "--min-severity" not in run_commands
    assert "uv run semgrep scan --config .semgrep.yml --error" in run_commands
    assert "uv run pre-commit run gitleaks --all-files" in run_commands
    assert "uv run pre-commit run actionlint --all-files" in run_commands
    assert "uv run cyclonedx-py environment .venv" in run_commands


def test_external_e2e_dispatch_is_maintainer_gated() -> None:
    """The /e2e broker should dispatch exact PR heads without running PR code."""
    workflow = yaml.safe_load(E2E_DISPATCH_WORKFLOW.read_text(encoding="utf-8"))
    workflow_text = E2E_DISPATCH_WORKFLOW.read_text(encoding="utf-8")
    job = workflow["jobs"]["dispatch"]
    run_commands = "\n".join(step.get("run", "") for step in job["steps"])

    assert "issue_comment" in workflow[True]
    assert "actions/checkout" not in workflow_text
    assert "pull_request_target" not in workflow_text
    assert "TFBD_E2E_DISPATCH_TOKEN" in workflow_text
    assert "TFBD_STATUS_TOKEN" not in workflow_text
    assert "/e2e" in workflow_text
    assert "admin|maintain|write" in run_commands
    assert "review_decision" in run_commands
    assert 'review_decision}" != "APPROVED"' in run_commands
    assert "gh pr checks" in run_commands
    assert "terraform-branch-deploy/e2e" in run_commands
    assert "current_head_sha" in run_commands
    assert "actions/workflows/e2e-tests.yml/dispatches" in run_commands
