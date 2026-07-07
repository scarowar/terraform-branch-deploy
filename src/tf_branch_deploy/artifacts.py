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
from urllib.parse import quote

from .lifecycle import github_cli_env

logger = logging.getLogger(__name__)

PLAN_ARTIFACT_NAME_RE = re.compile(
    r"^(?P<params_hash>no-args|[0-9a-f]{8})-(?P<run_id>\d+)-(?P<run_attempt>\d+)$"
)

PLAN_META_SUFFIX = ".meta.json"

ARTIFACTS_PER_PAGE = 100
MAX_ARTIFACT_LIST_PAGES = 10
GH_LIST_TIMEOUT_SECONDS = 60
GH_DOWNLOAD_TIMEOUT_SECONDS = 120

# Plan zips are downloaded into memory and extracted member-by-member; these
# bounds keep a corrupted or malicious artifact (e.g. a decompression bomb)
# from exhausting runner memory or disk. Real Terraform plans are far smaller.
MAX_ARTIFACT_DOWNLOAD_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_MEMBER_BYTES = 512 * 1024 * 1024


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


def plan_intent_prefix(environment: str, sha: str) -> str:
    """Return the workflow artifact name prefix for a plan intent record.

    Intent records are uploaded before Terraform runs and share the plan
    artifact's name suffix, so the intent deterministically names the exact
    plan artifact the run was meant to produce.
    """
    return f"tfplan-intent-{environment}-{sha}-"


def plan_artifact_name_from_intent(intent_name: str, environment: str, sha: str) -> str:
    """Return the exact plan artifact name declared by an intent record."""
    suffix = intent_name.removeprefix(plan_intent_prefix(environment, sha))
    return plan_artifact_prefix(environment, sha) + suffix


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
    meta_path = plan_file.with_suffix(PLAN_META_SUFFIX)
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
    meta_path = plan_file.with_suffix(PLAN_META_SUFFIX)
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
    params_hash: str
    run_id: int
    run_attempt: int


@dataclass
class PlanArtifactStore:
    """Lists and downloads saved plan workflow artifacts via the GitHub API.

    Uses the gh CLI as the API transport (consistent with lifecycle management).
    Requires `actions: read` on the token to list and download artifacts.
    """

    repo: str
    github_token: str | None = None

    def resolve_latest_intent(self, environment: str, sha: str) -> PlanArtifactCandidate | None:
        """Return the newest valid plan intent record for this environment and commit.

        Intents are uploaded at the start of every plan run, so the newest
        intent identifies the plan the most recent `.plan` command was meant
        to produce — even when that run later failed. Selection is an explicit
        numeric sort by (run_id, run_attempt); the API's list order is never
        relied upon. Fork-uploaded and expired records are rejected. Returns
        None when no intent exists; raises PlanArtifactError when the listing
        fails or is truncated by the page cap, so an incomplete search can
        never masquerade as "no plan".
        """
        candidates = self._collect(plan_intent_prefix(environment, sha))
        if not candidates:
            return None
        return max(candidates, key=lambda c: (c.run_id, c.run_attempt))

    def find_exact(self, name: str, environment: str, sha: str) -> PlanArtifactCandidate | None:
        """Return the plan artifact with exactly this name, if it exists and is valid.

        Uses the API's exact-name filter, then applies the same provenance and
        expiry checks as intent resolution. When re-runs produced several
        artifacts with the same name, the highest artifact id (newest) wins.
        """
        prefix = plan_artifact_prefix(environment, sha)
        candidates = [
            candidate for candidate in self._collect(prefix, name=name) if candidate.name == name
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda c: c.id)

    def _collect(self, prefix: str, name: str | None = None) -> list[PlanArtifactCandidate]:
        """Collect all valid candidates matching a name prefix across pages.

        The listing is complete once a page is empty or the API-reported
        total_count has been covered — a short or final page is never mistaken
        for truncation. Only a genuinely unfinished scan raises, so an
        incomplete search can never masquerade as "no plan".
        """
        candidates: list[PlanArtifactCandidate] = []
        for page in range(1, MAX_ARTIFACT_LIST_PAGES + 1):
            artifacts, total_count = self._list_page(page, name=name)
            for raw in artifacts:
                candidate = self._accept(raw, prefix)
                if candidate is not None:
                    candidates.append(candidate)
            if not artifacts or page * ARTIFACTS_PER_PAGE >= total_count:
                return candidates
        raise PlanArtifactError(
            "Artifact search truncated after "
            f"{MAX_ARTIFACT_LIST_PAGES * ARTIFACTS_PER_PAGE} artifacts; "
            "cannot reliably determine the latest plan intent. Reduce artifact volume "
            "or retention in this repository."
        )

    def download_and_extract(
        self,
        candidate: PlanArtifactCandidate,
        dest_dir: Path,
        environment: str,
    ) -> list[Path]:
        """Download an artifact zip and extract the plan files into dest_dir.

        Archive members are extracted by basename only (upload-artifact flattens
        paths to the least common ancestor, so stored paths are not trusted).
        Members with absolute paths, traversal components, unexpected names, or
        decompression-bomb sizes abort the restore.
        """
        if candidate.size_in_bytes > MAX_ARTIFACT_DOWNLOAD_BYTES:
            raise PlanArtifactError(
                f"Plan artifact '{candidate.name}' is {candidate.size_in_bytes} bytes, "
                f"exceeding the {MAX_ARTIFACT_DOWNLOAD_BYTES}-byte safety limit"
            )

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
                        if member.file_size > MAX_EXTRACTED_MEMBER_BYTES:
                            raise PlanArtifactError(
                                f"Plan artifact '{candidate.name}' member "
                                f"{member.filename!r} would extract to "
                                f"{member.file_size} bytes, exceeding the "
                                f"{MAX_EXTRACTED_MEMBER_BYTES}-byte safety limit"
                            )
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

    def _list_page(self, page: int, name: str | None = None) -> tuple[list[dict], int]:
        """Return one page of artifacts plus the API-reported total count."""
        endpoint = f"repos/{self.repo}/actions/artifacts?per_page={ARTIFACTS_PER_PAGE}&page={page}"
        if name:
            endpoint += f"&name={quote(name)}"
        cmd = ["gh", "api", endpoint]
        try:
            result = subprocess.run(  # nosec B603
                cmd,
                capture_output=True,
                text=True,
                env=github_cli_env(self.github_token),
                check=False,
                timeout=GH_LIST_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise PlanArtifactError(
                f"Timed out listing workflow artifacts after {GH_LIST_TIMEOUT_SECONDS}s"
            ) from e
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
        total_count = payload.get("total_count", 0)
        if not isinstance(artifacts, list) or not isinstance(total_count, int):
            raise PlanArtifactError("Unexpected workflow artifacts response shape")
        return artifacts, total_count

    def _download_zip(self, candidate: PlanArtifactCandidate) -> bytes:
        # Binary stdout: artifact zips must not go through text decoding.
        cmd = [
            "gh",
            "api",
            f"repos/{self.repo}/actions/artifacts/{candidate.id}/zip",
        ]
        try:
            result = subprocess.run(  # nosec B603
                cmd,
                capture_output=True,
                env=github_cli_env(self.github_token),
                check=False,
                timeout=GH_DOWNLOAD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise PlanArtifactError(
                f"Timed out downloading plan artifact '{candidate.name}' "
                f"after {GH_DOWNLOAD_TIMEOUT_SECONDS}s"
            ) from e
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise PlanArtifactError(
                f"Failed to download plan artifact '{candidate.name}' "
                f"(gh exit {result.returncode}): {stderr}"
            )
        return result.stdout

    @staticmethod
    def _accept(raw: dict, prefix: str) -> PlanArtifactCandidate | None:
        name = raw.get("name", "")
        if not name.startswith(prefix):
            return None
        match = PLAN_ARTIFACT_NAME_RE.match(name.removeprefix(prefix))
        if match is None:
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

        run_id = int(match.group("run_id"))
        if workflow_run.get("id") != run_id:
            # The run id embedded in the name must match the run that actually
            # uploaded the artifact — a mismatch means the name was spoofed.
            logger.warning(
                "Rejected plan artifact '%s': name claims run %d but it was uploaded by run %s",
                name,
                run_id,
                workflow_run.get("id"),
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
            params_hash=match.group("params_hash"),
            run_id=run_id,
            run_attempt=int(match.group("run_attempt")),
        )

    @staticmethod
    def _safe_member_basename(member_name: str, environment: str, artifact_name: str) -> str:
        pure = PurePosixPath(member_name)
        if pure.is_absolute() or ".." in pure.parts or "\\" in member_name:
            raise PlanArtifactError(
                f"Plan artifact '{artifact_name}' contains an unsafe path: {member_name!r}"
            )
        basename = pure.name
        if not basename.startswith(f"tfplan-{environment}-") or not basename.endswith(
            (".tfplan", PLAN_META_SUFFIX)
        ):
            raise PlanArtifactError(
                f"Plan artifact '{artifact_name}' contains an unexpected file: {member_name!r}"
            )
        return basename
