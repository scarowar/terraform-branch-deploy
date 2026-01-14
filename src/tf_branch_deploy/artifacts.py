"""
Plan artifact management.

Handles storage, retrieval, and verification of Terraform plan binaries.
This is one of the THREE things we add on top of branch-deploy.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class PlanArtifact:
    """Metadata for a stored plan artifact."""

    environment: str
    sha: str
    checksum: str
    path: Path


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
