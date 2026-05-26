"""Documentation contract tests."""

from pathlib import Path


ROOT = Path(__file__).parent.parent.parent
REMOVED_V0_2_INPUTS = {
    "skip",
    "working-directory",
    "uv-version",
    "allow-forks",
    "successful-deploy-labels",
    "failed-deploy-labels",
    "successful-noop-labels",
    "failed-noop-labels",
    "skip-successful-noop-labels-if-approved",
    "skip-successful-deploy-labels-if-approved",
    "merge-deploy-mode",
    "unlock-on-merge-mode",
    "environment-url-in-comment",
    "deploy-message-path",
}


def _user_markdown() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
    )


def _user_facing_text() -> str:
    return "\n".join(
        [
            _user_markdown(),
            *[
                path.read_text(encoding="utf-8")
                for path in sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"))
            ],
        ]
    )


def test_docs_do_not_advertise_targeted_rollback() -> None:
    """Rollback docs must not imply direct targeted rollback is supported."""
    markdown = _user_markdown()

    assert ".apply main to prod | -target" not in markdown
    assert ".apply main to dev | -target" not in markdown
    assert "target-only rollback" in markdown
    assert "Terraform does not provide a deterministic" in markdown


def test_docs_schema_url_is_published_by_docs_workflow() -> None:
    """Editor schema docs must point at a URL the docs workflow publishes."""
    markdown = _user_markdown()
    workflow = (ROOT / ".github" / "workflows" / "docs.yml").read_text(encoding="utf-8")

    assert (
        "https://raw.githubusercontent.com/scarowar/terraform-branch-deploy/v0/"
        "tf-branch-deploy.schema.json"
    ) not in markdown
    assert "https://scarowar.github.io/terraform-branch-deploy/schema.json" in markdown
    assert "cp tf-branch-deploy.schema.json site/schema.json" in workflow


def test_v0_2_migration_guide_documents_removed_inputs() -> None:
    """The upgrade guide must cover all removed public inputs."""
    guide = (ROOT / "docs" / "upgrading.md").read_text(encoding="utf-8")
    nav = (ROOT / "zensical.toml").read_text(encoding="utf-8")
    missing = sorted(input_name for input_name in REMOVED_V0_2_INPUTS if input_name not in guide)

    assert not missing
    assert "GitHub Actions warns about unknown inputs and then ignores them" in guide
    assert "v0.1.0 to v0.2.0" in guide
    assert "upgrading.md" in nav


def test_docs_do_not_force_moving_major_action_ref() -> None:
    """Workflow examples must not make the moving v0 tag look mandatory."""
    markdown = _user_facing_text()

    assert "scarowar/terraform-branch-deploy@v0" not in markdown
    assert "scarowar/terraform-branch-deploy@<terraform-branch-deploy-ref>" in markdown
    assert "exact release tag or full commit SHA" in markdown


def test_reference_examples_explain_action_ref_placeholder() -> None:
    """Reference examples should be clear when users land on them directly."""
    commands = (ROOT / "docs" / "reference" / "commands.md").read_text(encoding="utf-8")
    outputs = (ROOT / "docs" / "reference" / "outputs.md").read_text(encoding="utf-8")

    for page in [commands, outputs]:
        assert "scarowar/terraform-branch-deploy@<terraform-branch-deploy-ref>" in page
        assert "Replace `<terraform-branch-deploy-ref>`" in page
        assert "exact release tag or full commit SHA" in page


def test_release_docs_match_action_ref_policy() -> None:
    """Release instructions must match the public docs action-ref policy."""
    release = (ROOT / "RELEASE.md").read_text(encoding="utf-8")

    assert "scarowar/terraform-branch-deploy@v0" not in release
    assert "scarowar/terraform-branch-deploy@<terraform-branch-deploy-ref>" in release
    assert "docs/includes/version.txt" not in release
    assert "scripts/update-version.sh" not in release


def test_changelog_is_public_release_history() -> None:
    """The changelog should stay factual and user-facing."""
    changelog_path = ROOT / "CHANGELOG.md"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = changelog_path.read_text(encoding="utf-8")
    lowered = changelog.lower()

    assert changelog_path.exists()
    assert "[Changelog](CHANGELOG.md)" in readme
    assert "## [0.2.0]" in changelog
    assert "## [0.1.0]" in changelog
    for phrase in [
        "conversation",
        "agent",
        "200%",
        "ai-generated",
        "we haven't",
        "for now",
        "future work",
        "deferred",
    ]:
        assert phrase not in lowered
