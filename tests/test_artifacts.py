"""Tests for artifacts module."""

import json
from pathlib import Path

from tf_branch_deploy.artifacts import (
    PlanMetadata,
    calculate_checksum,
    generate_artifact_name,
    generate_params_hash,
    load_plan_metadata,
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
        assert generate_params_hash(None) == "no-args"  # type: ignore[arg-type]

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
            "checksum": "abc123def456",
            "extra_args": ["-target=module.base"],
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
        assert loaded.checksum == original.checksum
        assert loaded.extra_args == original.extra_args
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

    def test_load_defaults_optional_fields(self, tmp_path: Path) -> None:
        """Metadata with only required field still loads with defaults."""
        plan_file = tmp_path / "tfplan-int-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        meta_path = plan_file.with_suffix(".meta.json")
        meta_path.write_text(json.dumps({"checksum": "abc123"}))

        loaded = load_plan_metadata(plan_file)
        assert loaded is not None
        assert loaded.checksum == "abc123"
        assert loaded.extra_args == []
        assert loaded.terraform_version == "unknown"

    def test_save_with_empty_extra_args(self, tmp_path: Path) -> None:
        plan_file = tmp_path / "tfplan-dev-abc12345.tfplan"
        plan_file.write_bytes(b"plan content")

        meta = self._make_metadata(extra_args=[])
        save_plan_metadata(plan_file, meta)
        loaded = load_plan_metadata(plan_file)

        assert loaded is not None
        assert loaded.extra_args == []
