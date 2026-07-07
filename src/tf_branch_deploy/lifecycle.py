"""
Github lifecycle management module.

Handles:
- Updating deployment status
- Managing reactions (initial/result)
- Posting result comments
- Managing environment locks
"""

from __future__ import annotations

import json
import os
import subprocess  # nosec B404
from dataclasses import dataclass
from typing import Any

from rich.console import Console

console = Console()


def branch_deploy_lock_ref(environment: str) -> str:
    """Return the lock ref name used by github/branch-deploy."""
    return f"{environment.replace(' ', '-')}-branch-deploy-lock"


def github_cli_env(token: str | None) -> dict[str, str]:
    """Build environment variables required by gh across GitHub hosts.

    Supports:
    - github.com (uses GITHUB_TOKEN)
    - ghe.com subdomains (uses GH_TOKEN)
    - Self-hosted GHE Server (uses GH_ENTERPRISE_TOKEN + GH_HOST)
    """
    env = os.environ.copy()
    if token:
        env["GITHUB_TOKEN"] = token  # github.com
        env["GH_TOKEN"] = token  # ghe.com
        env["GH_ENTERPRISE_TOKEN"] = token  # Self-hosted GHE

    host = _github_enterprise_host(env)
    if host:
        env["GH_HOST"] = host
    return env


def _github_enterprise_host(env: dict[str, str]) -> str | None:
    """Return the gh host for GitHub Enterprise Server, if configured."""
    server_url = env.get("GITHUB_SERVER_URL")
    if not server_url:
        return None

    from urllib.parse import urlparse

    host = urlparse(server_url).netloc
    return host if host and host != "github.com" else None


class GitHubApiError(RuntimeError):
    """Raised when a required GitHub CLI API call fails."""

    def __init__(self, cmd: list[str], stderr: str, returncode: int) -> None:
        self.cmd = cmd
        self.stderr = stderr
        self.returncode = returncode
        super().__init__(f"gh api failed with exit {returncode}: {stderr}")

    @property
    def is_not_found(self) -> bool:
        """Whether the API failure represents a missing resource."""
        return "HTTP 404" in self.stderr or "Not Found" in self.stderr


@dataclass
class LifecycleManager:
    """Manages the GitHub PR lifecycle for deployments."""

    repo: str
    github_token: str | None = None

    def update_deployment_status(self, deployment_id: str, state: str, environment: str) -> None:
        """Update GitHub deployment status."""
        if not deployment_id:
            return

        console.print(f"   📊 Updating deployment status to: {state}")
        self._gh_api(
            "POST",
            f"repos/{self.repo}/deployments/{deployment_id}/statuses",
            state=state,
            environment=environment,
        )

    def remove_reaction(self, comment_id: str, reaction_id: str) -> None:
        """Remove a reaction from a comment."""
        if not comment_id or not reaction_id:
            return

        console.print("   🗑️  Removing initial reaction")
        # Removing reaction uses DELETE method
        try:
            cmd = [
                "gh",
                "api",
                "--method",
                "DELETE",
                f"repos/{self.repo}/issues/comments/{comment_id}/reactions/{reaction_id}",
            ]
            self._run_gh(cmd)
        except Exception as e:
            console.print(
                f"[yellow]⚠️  Non-critical: failed to remove reaction "
                f"(comment={comment_id}, reaction={reaction_id}): {e}[/yellow]"
            )

    def add_reaction(self, comment_id: str, content: str) -> None:
        """Add a reaction to a comment."""
        if not comment_id:
            return

        console.print(f"   ✨ Adding {content} reaction")
        self._gh_api(
            "POST",
            f"repos/{self.repo}/issues/comments/{comment_id}/reactions",
            content=content,
        )

    def post_result_comment(self, pr_number: str, body: str) -> None:
        """Post a comment to the PR."""
        if not pr_number:
            return

        console.print("   💬 Posting deployment result comment")
        self._gh_api(
            "POST",
            f"repos/{self.repo}/issues/{pr_number}/comments",
            body=body,
        )

    def format_result_comment(
        self,
        status: str,
        env_vars: dict[str, str],
        failure_reason: str | None = None,
    ) -> str:
        """Format the result comment body."""
        actor = env_vars.get("TF_BD_ACTOR", "unknown")
        ref = env_vars.get("TF_BD_REF", "unknown")
        env = env_vars.get("TF_BD_ENVIRONMENT", "unknown")
        noop = env_vars.get("TF_BD_NOOP", "false").lower() == "true"

        deploy_type = "**noop** deployed" if noop else "deployed"

        if status == "success":
            header = "### Deployment Results ✅"
            msg = f"**{actor}** successfully {deploy_type} branch `{ref}` to **{env}**"
        else:
            header = "### ⚠️ Cannot proceed with deployment"
            msg = (
                failure_reason
                or "An unexpected error occurred. Please review the workflow logs for details."
            )

        metadata = self._generate_metadata(env_vars)

        return f"{header}\n\n{msg}\n\n<details><summary>Details</summary>\n\n```json\n{json.dumps(metadata, indent=2)}\n```\n\n</details>"

    def _generate_metadata(self, env_vars: dict[str, str]) -> dict[str, Any]:
        """Generate metadata JSON for the comment."""
        return {
            "type": env_vars.get("TF_BD_TYPE"),
            "environment": {"name": env_vars.get("TF_BD_ENVIRONMENT")},
            "deployment": {"id": env_vars.get("TF_BD_DEPLOYMENT_ID")},
            "git": {
                "ref": env_vars.get("TF_BD_REF"),
                "commit": env_vars.get("TF_BD_SHA"),
            },
            "context": {
                "actor": env_vars.get("TF_BD_ACTOR"),
                "noop": env_vars.get("TF_BD_NOOP", "false").lower() == "true",
            },
        }

    def remove_non_sticky_lock(self, environment: str) -> None:
        """Remove lock if it's not sticky."""
        lock_ref = branch_deploy_lock_ref(environment)
        console.print("   🔓 Checking for non-sticky lock")

        try:
            content_json = self._gh_api_get_content(
                f"repos/{self.repo}/contents/lock.json", ref=lock_ref
            )
            sticky = content_json.get("sticky", "false")
        except GitHubApiError as e:
            if e.is_not_found:
                console.print("   🔓 No active environment lock found")
                return
            msg = f"Failed to read lock metadata for environment={environment}: {e}"
            console.print(f"[red]❌ {msg}[/red]")
            raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Failed to parse lock metadata for environment={environment}: {e}"
            console.print(f"[red]❌ {msg}[/red]")
            raise RuntimeError(msg) from e

        if str(sticky).lower() == "true":
            console.print("   🔒 Lock is sticky - preserving")
            return

        console.print("   🗑️  Removing non-sticky lock")
        try:
            cmd = [
                "gh",
                "api",
                "--method",
                "DELETE",
                f"repos/{self.repo}/git/refs/heads/{lock_ref}",
            ]
            self._run_gh(cmd, raise_on_error=True)
        except Exception as e:
            msg = f"Failed to remove non-sticky lock for environment={environment}: {e}"
            console.print(f"[red]❌ {msg}[/red]")
            raise RuntimeError(msg) from e

    def _gh_api(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        """Call gh api."""
        args = ["gh", "api", "--method", method, endpoint]
        for k, v in kwargs.items():
            args.extend(["-f", f"{k}={v}"])

        return self._run_gh(args)

    def _gh_api_get_content(self, endpoint: str, ref: str) -> dict[str, Any]:
        """Get file content from GitHub API.

        Raises on any failure so callers can handle it explicitly.
        """
        import base64

        cmd = ["gh", "api", "--method", "GET", endpoint, "-f", f"ref={ref}", "--jq", ".content"]
        result = self._run_gh(cmd, capture_output=True, raise_on_error=True)
        if not result:
            raise RuntimeError("gh api returned empty response")

        decoded = base64.b64decode(result).decode("utf-8")
        return json.loads(decoded)

    def _run_gh(
        self,
        cmd: list[str],
        capture_output: bool = False,
        raise_on_error: bool = False,
    ) -> str | None:
        """Run gh command.

        Supports:
        - github.com (uses GITHUB_TOKEN)
        - ghe.com subdomains (uses GH_TOKEN)
        - Self-hosted GHE Server (uses GH_ENTERPRISE_TOKEN + GH_HOST)
        """
        env = self._github_cli_env()
        try:
            result = subprocess.run(  # nosec B603
                cmd, capture_output=True, text=True, env=env, check=False
            )
        except Exception as error:
            return self._handle_gh_exception(cmd, error, raise_on_error)

        return self._handle_gh_result(cmd, result, capture_output, raise_on_error)

    def _github_cli_env(self) -> dict[str, str]:
        """Build environment variables required by gh across GitHub hosts."""
        return github_cli_env(self.github_token)

    def _handle_gh_result(
        self,
        cmd: list[str],
        result: subprocess.CompletedProcess[str],
        capture_output: bool,
        raise_on_error: bool,
    ) -> str | None:
        """Return gh stdout or handle a non-zero gh exit."""
        if result.returncode == 0:
            return result.stdout.strip()

        stderr = result.stderr.strip()
        if raise_on_error:
            raise GitHubApiError(cmd=cmd, stderr=stderr, returncode=result.returncode)
        if not capture_output:
            console.print(
                f"[yellow]⚠️  gh command failed (exit {result.returncode}): {stderr}[/yellow]"
            )
        return None

    @staticmethod
    def _handle_gh_exception(
        cmd: list[str],
        error: Exception,
        raise_on_error: bool,
    ) -> str | None:
        """Convert gh execution exceptions into the caller's expected shape."""
        if raise_on_error:
            raise GitHubApiError(cmd=cmd, stderr=str(error), returncode=1) from error
        console.print(f"[red]Error running gh: {error}[/red]")
        return None
