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


@dataclass
class LifecycleManager:
    """Manages the GitHub PR lifecycle for deployments."""

    repo: str
    github_token: str | None = None

    def update_deployment_status(
        self, deployment_id: str, state: str, environment: str
    ) -> None:
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
                "gh", "api", "--method", "DELETE",
                f"repos/{self.repo}/issues/comments/{comment_id}/reactions/{reaction_id}"
            ]
            self._run_gh(cmd)
        except Exception as e:
            # Ignore errors removing reactions, but log for debug
            console.print(f"[dim]Ignored error removing reaction: {e}[/dim]")

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

    def post_result_comment(
        self, pr_number: str, body: str
    ) -> None:
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
            msg = failure_reason or "An unexpected error occurred. Please review the workflow logs for details."

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
        lock_ref = f"{environment}-branch-deploy-lock"
        console.print("   🔓 Checking for non-sticky lock")

        # 1. Get lock content
        try:
            content_json = self._gh_api_get_content(f"repos/{self.repo}/contents/lock.json", ref=lock_ref)
            sticky = content_json.get("sticky", "false")
        except Exception:
            sticky = "false"

        if str(sticky).lower() == "true":
            console.print("   🔒 Lock is sticky - preserving")
            return

        console.print("   🗑️  Removing non-sticky lock")
        try:
            cmd = ["gh", "api", "--method", "DELETE", f"repos/{self.repo}/git/refs/heads/{lock_ref}"]
            self._run_gh(cmd)
        except Exception as e:
            console.print(f"[dim]Ignored error removing lock: {e}[/dim]")

    def _gh_api(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        """Call gh api."""
        args = ["gh", "api", "--method", method, endpoint]
        for k, v in kwargs.items():
            args.extend(["-f", f"{k}={v}"])
        
        return self._run_gh(args)

    def _gh_api_get_content(self, endpoint: str, ref: str) -> dict[str, Any]:
        """Get file content from GitHub API."""
        # Using gh api to get raw content is tricky with base64 decoding.
        # Use jq to extract content and decode.
        # Can we rely on python's json/base64?
        # Let's use `gh api ... --jq .content` and decode in python.
        import base64
        
        cmd = ["gh", "api", endpoint, "-f", f"ref={ref}", "--jq", ".content"]
        result = self._run_gh(cmd, capture_output=True)
        if not result:
            return {}
            
        try:
            decoded = base64.b64decode(result).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            return {}

    def _run_gh(self, cmd: list[str], capture_output: bool = False) -> str | None:
        """Run gh command."""
        env = os.environ.copy()
        if self.github_token:
            env["GITHUB_TOKEN"] = self.github_token
            
        try:
            result = subprocess.run(  # nosec B603
                cmd,
                capture_output=True,
                text=True,
                env=env,
                check=False 
            )
            if result.returncode != 0:
                if not capture_output:
                    console.print(f"[dim]gh command failed: {result.stderr}[/dim]")
                return None
            return result.stdout.strip()
        except Exception as e:
            console.print(f"[red]Error running gh: {e}[/red]")
            return None
