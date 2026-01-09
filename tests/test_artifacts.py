"""Tests for artifacts module."""

from pathlib import Path

from tf_branch_deploy.artifacts import (
    calculate_checksum,
    generate_artifact_name,
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
