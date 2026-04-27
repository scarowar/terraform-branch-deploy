"""
Plan artifact management.

Handles storage, retrieval, and verification of Terraform plan binaries.
Provides metadata sidecar files for cross-run integrity verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlanArtifact:
    """Metadata for a stored plan artifact."""

    environment: str
    sha: str
    checksum: str
    path: Path


@dataclass(frozen=True)
class PlanMetadata:
    """Metadata recorded alongside a plan file for integrity verification.

    Persisted as a JSON sidecar (.meta.json) next to the .tfplan binary.
    Cached together with the plan so it survives across workflow runs.
    """

    checksum: str
    extra_args: list[str]
    terraform_version: str
    params_hash: str
    created_at: str


def calculate_checksum(file_path: Path) -> str:
    """
    Calculate SHA256 checksum of a plan file.

    Args:
        file_path: Path to the plan binary file.

    Returns:
        Hex-encoded SHA256 hash.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_checksum(file_path: Path, expected: str) -> bool:
    """
    Verify a plan file's checksum matches the expected value.

    Args:
        file_path: Path to the plan binary file.
        expected: Expected SHA256 hex hash.

    Returns:
        True if checksums match, False otherwise.
    """
    actual = calculate_checksum(file_path)
    return actual == expected


def generate_artifact_name(environment: str, sha: str) -> str:
    """
    Generate a consistent artifact name for a plan.

    Args:
        environment: Target deployment environment.
        sha: Git commit SHA.

    Returns:
        Artifact name like "tfplan-prod-abc123.tfplan"
    """
    return f"tfplan-{environment}-{sha[:8]}.tfplan"


def generate_params_hash(params: str) -> str:
    """
    Generate a stable hash of extra terraform parameters.

    Used to differentiate cache entries for the same commit
    with different plan arguments (e.g., -target=module.base vs full plan).

    Args:
        params: Raw extra params string (e.g., "-target=module.base").

    Returns:
        8-char hex hash, or "no-args" if params are empty.
    """
    stripped = params.strip() if params else ""
    if not stripped:
        return "no-args"
    return hashlib.sha256(stripped.encode()).hexdigest()[:8]


def save_plan_metadata(plan_file: Path, metadata: PlanMetadata) -> Path:
    """
    Save plan metadata as a JSON sidecar file alongside the plan.

    The sidecar is cached together with the plan file and provides
    integrity verification and an audit trail across workflow runs.

    Args:
        plan_file: Path to the .tfplan binary.
        metadata: Plan metadata to persist.

    Returns:
        Path to the created .meta.json file.
    """
    meta_path = plan_file.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "checksum": metadata.checksum,
                "extra_args": list(metadata.extra_args),
                "terraform_version": metadata.terraform_version,
                "params_hash": metadata.params_hash,
                "created_at": metadata.created_at,
            },
            indent=2,
        )
    )
    return meta_path


def load_plan_metadata(plan_file: Path) -> PlanMetadata | None:
    """
    Load plan metadata from the JSON sidecar file.

    Args:
        plan_file: Path to the .tfplan binary.

    Returns:
        PlanMetadata if sidecar exists and is valid, None otherwise.
    """
    meta_path = plan_file.with_suffix(".meta.json")
    if not meta_path.exists():
        return None
    try:
        data = json.loads(meta_path.read_text())
        return PlanMetadata(
            checksum=data["checksum"],
            extra_args=data.get("extra_args", []),
            terraform_version=data.get("terraform_version", "unknown"),
            params_hash=data.get("params_hash", "unknown"),
            created_at=data.get("created_at", "unknown"),
        )
    except (json.JSONDecodeError, KeyError):
        logger.warning("Failed to parse plan metadata sidecar: %s", meta_path)
        return None
