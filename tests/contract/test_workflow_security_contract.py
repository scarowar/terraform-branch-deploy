"""Security contracts for GitHub Actions workflows."""

from pathlib import Path
import re


REPO_ROOT = Path(__file__).parent.parent.parent
WORKFLOW_FILES = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
ACTION_FILES = [REPO_ROOT / "action.yml"]
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
