"""Documentation contract tests."""

from pathlib import Path


ROOT = Path(__file__).parent.parent.parent


def test_docs_do_not_advertise_targeted_rollback() -> None:
    """Rollback docs must not imply direct targeted rollback is supported."""
    markdown = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    )

    assert ".apply main to prod | -target" not in markdown
    assert ".apply main to dev | -target" not in markdown
    assert "target-only rollback" in markdown
    assert "Terraform does not provide a deterministic" in markdown
