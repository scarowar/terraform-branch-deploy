"""Security contracts for GitHub Actions workflows."""

from pathlib import Path
import re

import yaml


REPO_ROOT = Path(__file__).parent.parent.parent
WORKFLOW_FILES = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
ACTION_FILES = [REPO_ROOT / "action.yml"]
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"
E2E_DISPATCH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "e2e-dispatch.yml"
CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"
ACTION_REF_RE = re.compile(r"@[0-9a-f]{40}$")
PR_COST_CONTROL_WORKFLOWS = {
    "ci.yml",
    "codeql.yml",
    "dependency-review.yml",
    "security.yml",
    "sonarqube.yml",
}
PR_CONCURRENCY_GROUP = (
    "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"
)


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


def _load_workflow(name: str) -> dict:
    return yaml.safe_load((REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


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


def test_repository_has_codeowners_for_review_routing() -> None:
    """CODEOWNERS gives branch rulesets a maintainer ownership hook."""
    owners = CODEOWNERS.read_text(encoding="utf-8")

    assert "* @scarowar" in owners


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
            if path == E2E_DISPATCH_WORKFLOW and job_name == "parse":
                run_commands = "\n".join(step.get("run", "") for step in job.get("steps", []))
                assert "gh api" not in run_commands
                assert "actions/checkout" not in run_commands
                continue
            steps = job.get("steps", [])
            if not steps:
                continue
            first_step_uses = steps[0].get("uses", "")
            assert first_step_uses.startswith("step-security/harden-runner@"), (
                f"{path}:{job_name} does not start with Harden-Runner"
            )


def test_workflows_have_bounded_runtime() -> None:
    """Every job should have a timeout so a stuck runner cannot burn budget."""
    for path in WORKFLOW_FILES:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in workflow.get("jobs", {}).items():
            timeout = job.get("timeout-minutes")
            assert timeout, f"{path}:{job_name} is missing timeout-minutes"
            assert timeout <= 25, f"{path}:{job_name} timeout is too high"


def test_pull_request_workflows_cancel_superseded_runs() -> None:
    """New commits should cancel stale PR runs instead of running duplicate checks."""
    for workflow_name in PR_COST_CONTROL_WORKFLOWS:
        workflow = _load_workflow(workflow_name)
        concurrency = workflow["concurrency"]

        assert concurrency["group"] == PR_CONCURRENCY_GROUP
        assert concurrency["cancel-in-progress"] is True


def test_ci_lint_keeps_fast_quality_gates() -> None:
    """CI lint should avoid duplicating heavyweight pre-commit security hooks."""
    workflow = _load_workflow("ci.yml")
    steps = workflow["jobs"]["lint"]["steps"]
    run_commands = "\n".join(step.get("run", "") for step in steps)

    assert "uv run pre-commit run --all-files" not in run_commands
    assert "uv run ruff check ." in run_commands
    assert "uv run ruff format --check ." in run_commands
    assert "uv run mypy --ignore-missing-imports src tests" in run_commands
    assert "uv run zensical build --strict --clean" in run_commands


def test_low_signal_bot_prs_skip_expensive_duplicate_checks() -> None:
    """Bot-PR skips must never break required status check reporting.

    Non-matrix jobs (sonar, dependency-review, deterministic-security) may
    skip on bot PRs: a job-level skip still reports a skipped check under the
    job's exact name, which satisfies the ruleset's required check. The CodeQL
    job must NOT skip: its required context "Analyze (CodeQL) (python)" comes
    from matrix expansion, and a job-level skip prevents expansion, so the
    required context never reports and bot PRs become permanently unmergeable.
    """
    codeql = _load_workflow("codeql.yml")
    dependency_review = _load_workflow("dependency-review.yml")
    security = _load_workflow("security.yml")
    sonarqube = _load_workflow("sonarqube.yml")

    assert "if" not in codeql["jobs"]["analyze"]
    assert dependency_review["jobs"]["dependency-review"]["if"] == (
        "github.actor != 'pre-commit-ci[bot]'"
    )
    assert (
        "github.actor != 'pre-commit-ci[bot]'" in security["jobs"]["deterministic-security"]["if"]
    )
    assert "github.actor != 'dependabot[bot]'" in sonarqube["jobs"]["sonar"]["if"]
    assert "github.actor != 'pre-commit-ci[bot]'" in sonarqube["jobs"]["sonar"]["if"]


def test_docs_deploy_runs_only_when_docs_surface_changes() -> None:
    """The Pages deploy should not run on code-only pushes to main."""
    workflow = _load_workflow("docs.yml")
    paths = workflow[True]["push"]["paths"]

    assert ".github/workflows/docs.yml" in paths
    assert "docs/**" in paths
    assert "tf-branch-deploy.schema.json" in paths
    assert "zensical.toml" in paths


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


def test_sonarqube_workflow_reports_python_coverage() -> None:
    """SonarQube quality gates need coverage data from the CI scanner."""
    workflow = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "sonarqube.yml").read_text(encoding="utf-8")
    )
    properties = (REPO_ROOT / "sonar-project.properties").read_text(encoding="utf-8")
    steps = workflow["jobs"]["sonar"]["steps"]
    job_condition = workflow["jobs"]["sonar"]["if"]
    run_commands = "\n".join(step.get("run", "") for step in steps)

    assert "pull_request" in workflow[True]
    assert "push" in workflow[True]
    assert "workflow_dispatch" in workflow[True]
    assert "pull_request_target" not in workflow[True]
    assert "github.actor != 'dependabot[bot]'" in job_condition
    assert "github.actor != 'pre-commit-ci[bot]'" in job_condition
    assert "github.event.pull_request.head.repo.full_name == github.repository" in job_condition
    assert "uv sync --frozen --all-groups" in run_commands
    assert "--cov=src/tf_branch_deploy" in run_commands
    assert "--cov-report=xml:coverage.xml" in run_commands
    assert "sonar.python.coverage.reportPaths=coverage.xml" in properties


def test_external_e2e_dispatch_is_maintainer_gated() -> None:
    """The /e2e broker should dispatch exact PR heads without running PR code."""
    workflow = yaml.safe_load(E2E_DISPATCH_WORKFLOW.read_text(encoding="utf-8"))
    workflow_text = E2E_DISPATCH_WORKFLOW.read_text(encoding="utf-8")
    parse_job = workflow["jobs"]["parse"]
    job = workflow["jobs"]["dispatch"]
    parse_commands = "\n".join(step.get("run", "") for step in parse_job["steps"])
    run_commands = "\n".join(step.get("run", "") for step in job["steps"])

    assert "issue_comment" in workflow[True]
    assert "actions/checkout" not in workflow_text
    assert "pull_request_target" not in workflow_text
    assert "issues" not in workflow["permissions"]
    assert "issues" not in job["permissions"]
    assert job["needs"] == "parse"
    assert "TFBD_E2E_DISPATCH_TOKEN" in workflow_text
    assert "TFBD_STATUS_TOKEN" not in workflow_text
    assert "/e2e" in workflow_text
    assert "GITHUB_EVENT_PATH" in parse_commands
    assert "gh api" not in parse_commands
    assert "GH_TOKEN: ${{ secrets.TFBD_E2E_DISPATCH_TOKEN }}" in workflow_text
    assert "GH_TOKEN: ${{ github.token }}" not in workflow_text
    assert run_commands.index('if [ -z "${GH_TOKEN}" ]; then') < run_commands.index(
        '"repos/${SOURCE_REPOSITORY}/collaborators/${COMMENT_AUTHOR}/permission"'
    )
    assert run_commands.index('if [ -z "${GH_TOKEN}" ]; then') < run_commands.index(
        '"repos/${SOURCE_REPOSITORY}/commits/${candidate_ref}/status"'
    )
    assert "admin|maintain|write" in run_commands
    assert "reviewDecision" not in workflow_text
    assert "review_decision" not in run_commands
    assert "gh pr checks" in run_commands
    assert "terraform-branch-deploy/e2e" in run_commands
    assert "current_head_sha" in run_commands
    assert "commits/${candidate_ref}/status" in run_commands
    assert "already running for this pull request head" in run_commands
    assert "already passed for this pull request head" in run_commands
    assert "actions/workflows/e2e-tests.yml/dispatches" in run_commands
    assert "issues/${PR_NUMBER}/comments" in run_commands
    assert "issues/comments/${tracking_comment_id}" in run_commands
    assert "tracking_comment_id" in run_commands
