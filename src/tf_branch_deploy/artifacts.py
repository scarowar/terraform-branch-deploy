"""
Plan artifact management.

Handles storage, retrieval, and verification of Terraform plan binaries.
Provides metadata sidecar files for cross-run integrity verification and
persists plans across workflow runs as immutable workflow artifacts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess  # nosec B404
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .lifecycle import github_cli_env

logger = logging.getLogger(__name__)

PLAN_ARTIFACT_NAME_RE = re.compile(r"^(?P<params_hash>no-args|[0-9a-f]{8})-\d+-\d+$")

MAX_ARTIFACT_LIST_PAGES = 10


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

    environment: str
    sha: str
    checksum: str
    extra_args: list[str]
    plan_args: list[str]
    var_files: list[str]
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


def generate_params_hash(params: str | None) -> str:
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


def plan_artifact_prefix(environment: str, sha: str) -> str:
    """Return the workflow artifact name prefix for a plan.

    Full artifact names are "tfplan-{env}-{sha}-{params_hash}-{run_id}-{run_attempt}".
    """
    return f"tfplan-{environment}-{sha}-"


def params_hash_from_artifact_name(
    name: str | None,
    environment: str,
    sha: str,
) -> str | None:
    """Extract the saved plan params hash from a workflow artifact name."""
    if not name:
        return None

    prefix = plan_artifact_prefix(environment, sha)
    if not name.startswith(prefix):
        return None

    if match := PLAN_ARTIFACT_NAME_RE.match(name.removeprefix(prefix)):
        return match.group("params_hash")
    return None


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
                "environment": metadata.environment,
                "sha": metadata.sha,
                "checksum": metadata.checksum,
                "extra_args": list(metadata.extra_args),
                "plan_args": list(metadata.plan_args),
                "var_files": list(metadata.var_files),
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
            environment=data["environment"],
            sha=data["sha"],
            checksum=data["checksum"],
            extra_args=data["extra_args"],
            plan_args=data["plan_args"],
            var_files=data["var_files"],
            terraform_version=data["terraform_version"],
            params_hash=data["params_hash"],
            created_at=data["created_at"],
        )
    except (json.JSONDecodeError, KeyError):
        logger.warning("Failed to parse plan metadata sidecar: %s", meta_path)
        return None


class PlanArtifactError(RuntimeError):
    """Raised when a plan artifact cannot be listed, downloaded, or extracted."""


@dataclass(frozen=True)
class PlanArtifactCandidate:
    """A workflow artifact holding a saved plan, as reported by the GitHub API."""

    id: int
    name: str
    created_at: str
    expired: bool
    size_in_bytes: int
    repository_id: int | None
    head_repository_id: int | None
    workflow_run_id: int | None


@dataclass
class PlanArtifactStore:
    """Lists and downloads saved plan workflow artifacts via the GitHub API.

    Uses the gh CLI as the API transport (consistent with lifecycle management).
    Requires `actions: read` on the token to list and download artifacts.
    """

    repo: str
    github_token: str | None = None

    def find_latest(self, environment: str, sha: str) -> PlanArtifactCandidate | None:
        """Return the newest valid plan artifact for this environment and commit.

        The artifacts API returns newest-first, so the first accepted match is
        the latest plan — a newer successful plan supersedes older plans for
        the same environment and commit. Fork-uploaded and expired artifacts
        are rejected. Returns None when no valid artifact exists; raises
        PlanArtifactError when the API cannot be queried at all.
        """
        for page in range(1, MAX_ARTIFACT_LIST_PAGES + 1):
            artifacts = self._list_page(page)
            if not artifacts:
                return None
            for raw in artifacts:
                candidate = self._accept(raw, environment, sha)
                if candidate is not None:
                    return candidate
        logger.warning(
            "Stopped searching for plan artifacts after %d pages", MAX_ARTIFACT_LIST_PAGES
        )
        return None

    def download_and_extract(
        self,
        candidate: PlanArtifactCandidate,
        dest_dir: Path,
        environment: str,
    ) -> list[Path]:
        """Download an artifact zip and extract the plan files into dest_dir.

        Archive members are extracted by basename only (upload-artifact flattens
        paths to the least common ancestor, so stored paths are not trusted).
        Members with absolute paths, traversal components, or unexpected names
        abort the restore.
        """
        zip_bytes = self._download_zip(candidate)
        extracted: list[Path] = []
        try:
            with tempfile.TemporaryFile(dir=os.environ.get("RUNNER_TEMP")) as tmp:
                tmp.write(zip_bytes)
                tmp.seek(0)
                with zipfile.ZipFile(tmp) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        basename = self._safe_member_basename(
                            member.filename, environment, candidate.name
                        )
                        target = dest_dir / basename
                        target.write_bytes(archive.read(member))
                        extracted.append(target)
        except zipfile.BadZipFile as e:
            raise PlanArtifactError(
                f"Plan artifact '{candidate.name}' is not a valid zip archive: {e}"
            ) from e
        except OSError as e:
            raise PlanArtifactError(
                f"Failed to extract plan artifact '{candidate.name}': {e}"
            ) from e

        if not extracted:
            raise PlanArtifactError(f"Plan artifact '{candidate.name}' contained no plan files")
        return extracted

    def _list_page(self, page: int) -> list[dict]:
        cmd = [
            "gh",
            "api",
            f"repos/{self.repo}/actions/artifacts?per_page=100&page={page}",
        ]
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            env=github_cli_env(self.github_token),
            check=False,
        )
        if result.returncode != 0:
            raise PlanArtifactError(
                f"Failed to list workflow artifacts (gh exit {result.returncode}): "
                f"{result.stderr.strip()}"
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise PlanArtifactError(f"Failed to parse workflow artifacts response: {e}") from e
        artifacts = payload.get("artifacts", [])
        if not isinstance(artifacts, list):
            raise PlanArtifactError("Unexpected workflow artifacts response shape")
        return artifacts

    def _download_zip(self, candidate: PlanArtifactCandidate) -> bytes:
        # Binary stdout: artifact zips must not go through text decoding.
        cmd = [
            "gh",
            "api",
            f"repos/{self.repo}/actions/artifacts/{candidate.id}/zip",
        ]
        result = subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            env=github_cli_env(self.github_token),
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise PlanArtifactError(
                f"Failed to download plan artifact '{candidate.name}' "
                f"(gh exit {result.returncode}): {stderr}"
            )
        return result.stdout

    @staticmethod
    def _accept(raw: dict, environment: str, sha: str) -> PlanArtifactCandidate | None:
        name = raw.get("name", "")
        if params_hash_from_artifact_name(name, environment, sha) is None:
            return None
        if raw.get("expired"):
            logger.warning("Skipping expired plan artifact: %s", name)
            return None

        workflow_run = raw.get("workflow_run") or {}
        repository_id = workflow_run.get("repository_id")
        head_repository_id = workflow_run.get("head_repository_id")
        if repository_id is None or head_repository_id != repository_id:
            # Fork-PR runs can upload artifacts into the base repository, so an
            # artifact whose creating run did not execute against this repo's
            # own code could be a spoofed plan. Never apply it.
            logger.warning(
                "Rejected plan artifact '%s': uploaded from a fork repository "
                "or missing workflow run provenance",
                name,
            )
            return None

        return PlanArtifactCandidate(
            id=raw["id"],
            name=name,
            created_at=raw.get("created_at", ""),
            expired=False,
            size_in_bytes=raw.get("size_in_bytes", 0),
            repository_id=repository_id,
            head_repository_id=head_repository_id,
            workflow_run_id=workflow_run.get("id"),
        )

    @staticmethod
    def _safe_member_basename(member_name: str, environment: str, artifact_name: str) -> str:
        pure = PurePosixPath(member_name)
        if pure.is_absolute() or ".." in pure.parts or "\\" in member_name:
            raise PlanArtifactError(
                f"Plan artifact '{artifact_name}' contains an unsafe path: {member_name!r}"
            )
        basename = pure.name
        if not basename.startswith(f"tfplan-{environment}-") or not (
            basename.endswith(".tfplan") or basename.endswith(".meta.json")
        ):
            raise PlanArtifactError(
                f"Plan artifact '{artifact_name}' contains an unexpected file: {member_name!r}"
            )
        return basename
