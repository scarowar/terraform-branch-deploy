"""Tests for artifacts module."""

import io
import json
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tf_branch_deploy.artifacts import (
    PlanArtifactCandidate,
    PlanArtifactError,
    PlanArtifactStore,
    PlanMetadata,
    calculate_checksum,
    generate_artifact_name,
    generate_params_hash,
    load_plan_metadata,
    plan_artifact_name_from_intent,
    plan_artifact_prefix,
    plan_intent_prefix,
    save_plan_metadata,
    verify_checksum,
)


class TestChecksum:
    """Tests for checksum calculation and verification."""

    def test_calculate_checksum_deterministic(self, tmp_path: Path) -> None:
        """Same content produces same checksum."""
        file1 = tmp_path / "plan1.tfplan"
        file2 = tmp_path / "plan2.tfplan"

        content = b"terraform plan binary content"
        file1.write_bytes(content)
        file2.write_bytes(content)

        assert calculate_checksum(file1) == calculate_checksum(file2)

    def test_different_content_different_checksum(self, tmp_path: Path) -> None:
        """Different content produces different checksum."""
        file1 = tmp_path / "plan1.tfplan"
        file2 = tmp_path / "plan2.tfplan"

        file1.write_bytes(b"content A")
        file2.write_bytes(b"content B")

        assert calculate_checksum(file1) != calculate_checksum(file2)

    def test_verify_checksum_success(self, tmp_path: Path) -> None:
        """Verification passes for matching checksum."""
        plan_file = tmp_path / "plan.tfplan"
        plan_file.write_bytes(b"terraform plan")

        checksum = calculate_checksum(plan_file)

        assert verify_checksum(plan_file, checksum) is True

    def test_verify_checksum_failure(self, tmp_path: Path) -> None:
        """Verification fails for mismatched checksum."""
        plan_file = tmp_path / "plan.tfplan"
        plan_file.write_bytes(b"terraform plan")

        assert verify_checksum(plan_file, "wrong_checksum") is False


class TestArtifactNaming:
    """Tests for artifact name generation."""

    def test_generate_artifact_name(self) -> None:
        """Name includes environment and truncated SHA."""
        name = generate_artifact_name("prod", "abc123def456789")

        assert name == "tfplan-prod-abc123de.tfplan"
        assert "prod" in name
        assert name.endswith(".tfplan")

    def test_artifact_name_various_environments(self) -> None:
        """Test artifact naming with various environment names."""
        test_cases = [
            ("dev", "abc12345", "tfplan-dev-abc12345.tfplan"),
            ("prod", "def67890abc12345", "tfplan-prod-def67890.tfplan"),
            ("staging", "1234abcd", "tfplan-staging-1234abcd.tfplan"),
        ]

        for env, sha, expected in test_cases:
            result = generate_artifact_name(env, sha)
            assert result == expected, f"Failed for {env}, {sha}"

    def test_artifact_name_is_valid_filename(self) -> None:
        """Artifact name should be a valid filename."""
        name = generate_artifact_name("prod-eu", "abc123def456")

        assert "/" not in name
        assert "\\" not in name
        assert name.endswith(".tfplan")
        assert "prod-eu" in name


class TestParamsHash:
    """Tests for generate_params_hash."""

    def test_empty_params_returns_no_args(self) -> None:
        assert generate_params_hash("") == "no-args"

    def test_whitespace_only_returns_no_args(self) -> None:
        assert generate_params_hash("   ") == "no-args"

    def test_none_returns_no_args(self) -> None:
        assert generate_params_hash(None) == "no-args"

    def test_deterministic(self) -> None:
        """Same args produce same hash."""
        h1 = generate_params_hash("-target=module.base")
        h2 = generate_params_hash("-target=module.base")
        assert h1 == h2

    def test_different_args_different_hash(self) -> None:
        h1 = generate_params_hash("-target=module.base")
        h2 = generate_params_hash("-target=module.lambda")
        assert h1 != h2

    def test_hash_is_8_chars(self) -> None:
        h = generate_params_hash("-target=module.base")
        assert len(h) == 8
        assert h != "no-args"


class TestPlanMetadata:
    """Tests for PlanMetadata save/load round-trip."""

    def _make_metadata(self, **overrides: object) -> PlanMetadata:
        defaults: dict[str, object] = {
            "environment": "int",
            "sha": "abc12345ff",
            "checksum": "abc123def456",
            "extra_args": ["-target=module.base"],
            "plan_args": ["-parallelism=20", "-target=module.base"],
            "var_files": ["int.tfvars"],
            "terraform_version": "1.9.8",
            "params_hash": "a1b2c3d4",
            "created_at": "2025-01-15T10:30:00+00:00",
        }
        defaults.update(overrides)
        return PlanMetadata(**defaults)  # type: ignore[arg-type]

    def test_save_creates_meta_json(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        meta = self._make_metadata()
        meta_path = save_plan_metadata(plan_file, meta)

        assert meta_path.exists()
        assert meta_path.suffix == ".json"
        assert meta_path.name == "tfplan-int-abc12345.meta.json"

    def test_save_load_round_trip(self, tmp_path: Path) -> None:
        """Save then load returns identical metadata."""
        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        original = self._make_metadata()
        save_plan_metadata(plan_file, original)
        loaded = load_plan_metadata(plan_file)

        assert loaded is not None
        assert loaded.environment == original.environment
        assert loaded.sha == original.sha
        assert loaded.checksum == original.checksum
        assert loaded.extra_args == original.extra_args
        assert loaded.plan_args == original.plan_args
        assert loaded.var_files == original.var_files
        assert loaded.terraform_version == original.terraform_version
        assert loaded.params_hash == original.params_hash
        assert loaded.created_at == original.created_at

    def test_load_returns_none_when_no_sidecar(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        assert load_plan_metadata(plan_file) is None

    def test_load_returns_none_on_corrupt_json(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        meta_path = plan_file.with_suffix(".meta.json")
        meta_path.write_text("not valid json {{{")

        assert load_plan_metadata(plan_file) is None

    def test_load_returns_none_on_missing_required_fields(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        meta_path = plan_file.with_suffix(".meta.json")
        meta_path.write_text(json.dumps({"extra_args": []}))  # missing 'checksum'

        assert load_plan_metadata(plan_file) is None

    def test_load_rejects_legacy_metadata_without_context(self, tmp_path: Path) -> None:
        """Metadata without environment/SHA/args context is not enough to apply."""
        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        meta_path = plan_file.with_suffix(".meta.json")
        meta_path.write_text(json.dumps({"checksum": "abc123"}))

        assert load_plan_metadata(plan_file) is None

    def test_save_with_empty_extra_args(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "tfplan-dev-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        meta = self._make_metadata(extra_args=[])
        save_plan_metadata(plan_file, meta)
        loaded = load_plan_metadata(plan_file)

        assert loaded is not None
        assert loaded.extra_args == []


class TestPlanArtifactStore:
    """Tests for intent resolution and plan artifact download."""

    ENV = "int"
    SHA = "abc12345ff0000000000000000000000000000ff"

    @staticmethod
    def _artifact(
        name: str,
        *,
        artifact_id: int = 1,
        expired: bool = False,
        repo_id: int | None = 100,
        head_repo_id: int | None = 100,
        run_id: int | None = None,
        created_at: str = "2026-07-06T00:00:00Z",
    ) -> dict:
        if run_id is None:
            # Default the uploading run id to the one embedded in the name so
            # fixtures pass the spoof cross-check unless a test overrides it.
            tail = name.rsplit("-", 2)
            run_id = int(tail[1]) if len(tail) == 3 and tail[1].isdigit() else 0
        return {
            "id": artifact_id,
            "name": name,
            "created_at": created_at,
            "expired": expired,
            "size_in_bytes": 42,
            "workflow_run": {
                "id": run_id,
                "repository_id": repo_id,
                "head_repository_id": head_repo_id,
            },
        }

    def _intent_name(self, params_hash: str = "no-args", run: str = "123-1") -> str:
        return f"tfplan-intent-{self.ENV}-{self.SHA}-{params_hash}-{run}"

    def _plan_name(self, params_hash: str = "no-args", run: str = "123-1") -> str:
        return f"tfplan-{self.ENV}-{self.SHA}-{params_hash}-{run}"

    @staticmethod
    def _list_response(*artifacts: dict) -> MagicMock:
        return MagicMock(returncode=0, stdout=json.dumps({"artifacts": list(artifacts)}))

    def test_resolve_latest_intent_sorts_numerically_not_by_api_order(self) -> None:
        """Selection must not rely on the API's undocumented list order."""
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        oldest = self._artifact(self._intent_name(run="111-1"), artifact_id=1)
        newest = self._artifact(self._intent_name(run="333-1"), artifact_id=3)
        middle = self._artifact(self._intent_name(run="222-2"), artifact_id=2)

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            # Deliberately unordered: oldest first, newest in the middle.
            run_mock.side_effect = [
                self._list_response(oldest, newest, middle),
                self._list_response(),
            ]
            intent = store.resolve_latest_intent(self.ENV, self.SHA)

        assert intent is not None
        assert intent.run_id == 333
        assert intent.params_hash == "no-args"

    def test_resolve_latest_intent_prefers_higher_run_attempt(self) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        first = self._artifact(self._intent_name(run="123-1"), artifact_id=1)
        retry = self._artifact(self._intent_name(run="123-2"), artifact_id=2)

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.side_effect = [
                self._list_response(retry, first),
                self._list_response(),
            ]
            intent = store.resolve_latest_intent(self.ENV, self.SHA)

        assert intent is not None
        assert intent.run_attempt == 2

    def test_resolve_latest_intent_rejects_fork_uploaded_records(self) -> None:
        """A fork-PR run can upload artifacts into the base repo - never trust those."""
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        spoofed = self._artifact(self._intent_name(), head_repo_id=999)
        missing_provenance = dict(self._artifact(self._intent_name()), workflow_run=None)

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.side_effect = [
                self._list_response(spoofed, missing_provenance),
                self._list_response(),
            ]
            assert store.resolve_latest_intent(self.ENV, self.SHA) is None

    def test_resolve_latest_intent_rejects_run_id_spoof(self) -> None:
        """A name claiming a different run than its uploader is spoofed."""
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        spoofed = self._artifact(self._intent_name(run="999-1"), run_id=123)

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.side_effect = [
                self._list_response(spoofed),
                self._list_response(),
            ]
            assert store.resolve_latest_intent(self.ENV, self.SHA) is None

    def test_resolve_latest_intent_skips_expired_and_malformed_names(self) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        expired = self._artifact(self._intent_name(), expired=True)
        wrong_env = self._artifact(f"tfplan-intent-prod-{self.SHA}-no-args-123-1")
        plan_not_intent = self._artifact(self._plan_name())
        malformed = self._artifact(f"tfplan-intent-{self.ENV}-{self.SHA}-nope-123-1")
        unrelated = self._artifact("coverage-report")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.side_effect = [
                self._list_response(expired, wrong_env, plan_not_intent, malformed, unrelated),
                self._list_response(),
            ]
            assert store.resolve_latest_intent(self.ENV, self.SHA) is None

    def test_resolve_latest_intent_collects_across_pages(self) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        page1_match = self._artifact(self._intent_name(run="111-1"), artifact_id=1)
        page2_match = self._artifact(self._intent_name(run="222-1"), artifact_id=2)

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.side_effect = [
                self._list_response(page1_match),
                self._list_response(page2_match),
                self._list_response(),
            ]
            intent = store.resolve_latest_intent(self.ENV, self.SHA)

        assert intent is not None
        assert intent.run_id == 222
        assert "page=2" in run_mock.call_args_list[1].args[0][2]

    def test_resolve_latest_intent_returns_none_when_no_artifacts(self) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = self._list_response()
            assert store.resolve_latest_intent(self.ENV, self.SHA) is None

    def test_resolve_latest_intent_raises_when_page_cap_exhausted(self) -> None:
        """A truncated search must never masquerade as 'no plan'."""
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = self._list_response(self._artifact("unrelated"))
            with pytest.raises(PlanArtifactError, match="truncated"):
                store.resolve_latest_intent(self.ENV, self.SHA)

    def test_resolve_latest_intent_raises_when_listing_fails(self) -> None:
        """A failed listing (e.g. missing actions: read) is not the same as no plan."""
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(
                returncode=1, stdout="", stderr="HTTP 403: Resource not accessible"
            )
            with pytest.raises(PlanArtifactError, match="Failed to list workflow artifacts"):
                store.resolve_latest_intent(self.ENV, self.SHA)

    def test_resolve_latest_intent_raises_on_timeout(self) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.side_effect = subprocess.TimeoutExpired(cmd=["gh"], timeout=60)
            with pytest.raises(PlanArtifactError, match="Timed out listing"):
                store.resolve_latest_intent(self.ENV, self.SHA)

    def test_find_exact_uses_name_filter_and_matches(self) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        name = self._plan_name()
        match = self._artifact(name, artifact_id=7)

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = self._list_response(match)
            candidate = store.find_exact(name, self.ENV, self.SHA)

        assert candidate is not None
        assert candidate.id == 7
        assert f"name={name}" in run_mock.call_args.args[0][2]

    def test_find_exact_returns_none_when_absent(self) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = self._list_response()
            assert store.find_exact(self._plan_name(), self.ENV, self.SHA) is None

    def test_find_exact_rejects_fork_uploaded_plan(self) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        name = self._plan_name()
        spoofed = self._artifact(name, head_repo_id=999)

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = self._list_response(spoofed)
            assert store.find_exact(name, self.ENV, self.SHA) is None

    def _zip_bytes(self, *members: tuple[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as archive:
            for name, content in members:
                archive.writestr(name, content)
        return buf.getvalue()

    def _candidate(self) -> PlanArtifactCandidate:
        return PlanArtifactCandidate(
            id=7,
            name=self._plan_name(),
            created_at="2026-07-06T00:00:00Z",
            expired=False,
            size_in_bytes=42,
            repository_id=100,
            head_repository_id=100,
            workflow_run_id=123,
            params_hash="no-args",
            run_id=123,
            run_attempt=1,
        )

    def test_download_and_extract_restores_plan_files(self, tmp_path: Path) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        zip_bytes = self._zip_bytes(
            (f"tfplan-{self.ENV}-abc12345.tfplan", b"plan bytes"),
            (f"tfplan-{self.ENV}-abc12345.meta.json", b"{}"),
        )

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0, stdout=zip_bytes)
            extracted = store.download_and_extract(self._candidate(), tmp_path, self.ENV)

        assert sorted(p.name for p in extracted) == [
            f"tfplan-{self.ENV}-abc12345.meta.json",
            f"tfplan-{self.ENV}-abc12345.tfplan",
        ]
        assert (tmp_path / f"tfplan-{self.ENV}-abc12345.tfplan").read_bytes() == b"plan bytes"

    def test_download_and_extract_flattens_stored_paths(self, tmp_path: Path) -> None:
        """Stored member paths are never trusted - extraction is by basename only."""
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        zip_bytes = self._zip_bytes(
            (f"nested/dir/tfplan-{self.ENV}-abc12345.tfplan", b"plan bytes"),
            (f"nested/dir/tfplan-{self.ENV}-abc12345.meta.json", b"{}"),
        )

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0, stdout=zip_bytes)
            store.download_and_extract(self._candidate(), tmp_path, self.ENV)

        assert (tmp_path / f"tfplan-{self.ENV}-abc12345.tfplan").exists()
        assert not (tmp_path / "nested").exists()

    @pytest.mark.parametrize(
        "member_name",
        [
            "../tfplan-int-abc12345.tfplan",
            "/tmp/tfplan-int-abc12345.tfplan",
            "notes.txt",
            "tfplan-prod-abc12345.tfplan",
        ],
    )
    def test_download_and_extract_rejects_unsafe_members(
        self, tmp_path: Path, member_name: str
    ) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")
        zip_bytes = self._zip_bytes((member_name, b"malicious"))

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0, stdout=zip_bytes)
            with pytest.raises(PlanArtifactError):
                store.download_and_extract(self._candidate(), tmp_path, self.ENV)

    def test_download_and_extract_rejects_corrupt_zip(self, tmp_path: Path) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=0, stdout=b"not a zip")
            with pytest.raises(PlanArtifactError, match="not a valid zip archive"):
                store.download_and_extract(self._candidate(), tmp_path, self.ENV)

    def test_download_failure_raises(self, tmp_path: Path) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(returncode=1, stdout=b"", stderr=b"HTTP 410: Gone")
            with pytest.raises(PlanArtifactError, match="Failed to download plan artifact"):
                store.download_and_extract(self._candidate(), tmp_path, self.ENV)

    def test_download_timeout_raises(self, tmp_path: Path) -> None:
        store = PlanArtifactStore(repo="owner/repo", github_token="tok")

        with patch("tf_branch_deploy.artifacts.subprocess.run") as run_mock:
            run_mock.side_effect = subprocess.TimeoutExpired(cmd=["gh"], timeout=120)
            with pytest.raises(PlanArtifactError, match="Timed out downloading"):
                store.download_and_extract(self._candidate(), tmp_path, self.ENV)


class TestIntentNameHelpers:
    """Tests for intent-record naming helpers."""

    def test_plan_artifact_name_from_intent_round_trip(self) -> None:
        sha = "abc12345ff0000000000000000000000000000ff"
        intent = f"tfplan-intent-dev-{sha}-a1b2c3d4-555-2"

        assert (
            plan_artifact_name_from_intent(intent, "dev", sha) == f"tfplan-dev-{sha}-a1b2c3d4-555-2"
        )

    def test_intent_prefix_is_distinct_from_plan_prefix(self) -> None:
        sha = "abc12345ff0000000000000000000000000000ff"

        assert plan_intent_prefix("dev", sha) != plan_artifact_prefix("dev", sha)
        assert plan_intent_prefix("dev", sha).startswith("tfplan-intent-dev-")
