"""Tests for lifecycle module."""

import base64
import json
import os

from unittest.mock import MagicMock, patch

import pytest

from tf_branch_deploy.lifecycle import LifecycleManager, branch_deploy_lock_ref


def _gh_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    """Create a subprocess.run-like result for gh API tests."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _encoded_lock_metadata(sticky: str | bool) -> str:
    """Return base64-encoded lock.json content as GitHub contents API would."""
    data = json.dumps({"sticky": sticky}).encode("utf-8")
    return base64.b64encode(data).decode("ascii")


def _assert_relative_gh_api_args(args: list[str]) -> None:
    """gh api calls should use relative endpoints for GitHub Enterprise support."""
    assert all("://" not in arg for arg in args)


class TestLifecycleManager:
    """Tests for LifecycleManager."""

    @pytest.fixture
    def manager(self) -> LifecycleManager:
        """Create a LifecycleManager instance."""
        return LifecycleManager(repo="org/repo", github_token="test-token")

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_update_deployment_status(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test updating deployment status."""
        mock_run.return_value = _gh_result()

        manager.update_deployment_status("123", "success", "prod")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:4] == ["gh", "api", "--method", "POST"]
        assert "repos/org/repo/deployments/123/statuses" in args
        _assert_relative_gh_api_args(args)
        assert "state=success" in args

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_remove_reaction(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test removing reaction."""
        mock_run.return_value = _gh_result()

        manager.remove_reaction("456", "789")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:4] == ["gh", "api", "--method", "DELETE"]
        assert "repos/org/repo/issues/comments/456/reactions/789" in args
        _assert_relative_gh_api_args(args)

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_add_reaction(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test adding reaction."""
        mock_run.return_value = _gh_result()

        manager.add_reaction("456", "rocket")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:4] == ["gh", "api", "--method", "POST"]
        assert "repos/org/repo/issues/comments/456/reactions" in args
        _assert_relative_gh_api_args(args)
        assert "content=rocket" in args

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_post_result_comment(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test posting result comment."""
        mock_run.return_value = _gh_result()

        manager.post_result_comment("100", "body")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[:4] == ["gh", "api", "--method", "POST"]
        assert "repos/org/repo/issues/100/comments" in args
        _assert_relative_gh_api_args(args)
        assert "body=body" in args

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_lock_metadata_read_uses_explicit_get(
        self, mock_run: MagicMock, manager: LifecycleManager
    ) -> None:
        """Lock metadata reads must not let gh api switch to POST for -f ref."""
        mock_run.return_value = _gh_result(stdout=_encoded_lock_metadata("true"))

        manager.remove_non_sticky_lock("dev")

        args = mock_run.call_args[0][0]
        assert args[:4] == ["gh", "api", "--method", "GET"]
        assert "repos/org/repo/contents/lock.json" in args
        assert "ref=dev-branch-deploy-lock" in args
        assert "--jq" in args
        assert ".content" in args
        _assert_relative_gh_api_args(args)

    def test_lock_ref_name_matches_branch_deploy_space_normalization(self) -> None:
        """Lock cleanup must use the same branch name Branch Deploy creates."""
        assert branch_deploy_lock_ref("dev") == "dev-branch-deploy-lock"
        assert branch_deploy_lock_ref("team dev") == "team-dev-branch-deploy-lock"

    @pytest.mark.parametrize("sticky", ["false", False])
    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_non_sticky_lock_is_deleted(
        self, mock_run: MagicMock, manager: LifecycleManager, sticky: str | bool
    ) -> None:
        """Non-sticky deployment locks are removed after lifecycle completion."""
        mock_run.side_effect = [
            _gh_result(stdout=_encoded_lock_metadata(sticky)),
            _gh_result(),
        ]

        manager.remove_non_sticky_lock("dev")

        assert mock_run.call_count == 2
        delete_args = mock_run.call_args_list[1][0][0]
        assert delete_args[:4] == ["gh", "api", "--method", "DELETE"]
        assert "repos/org/repo/git/refs/heads/dev-branch-deploy-lock" in delete_args
        _assert_relative_gh_api_args(delete_args)

    @pytest.mark.parametrize("sticky", ["true", True])
    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_sticky_lock_is_preserved(
        self, mock_run: MagicMock, manager: LifecycleManager, sticky: str | bool
    ) -> None:
        """Sticky manual locks must remain until an explicit unlock command."""
        mock_run.return_value = _gh_result(stdout=_encoded_lock_metadata(sticky))

        manager.remove_non_sticky_lock("dev")

        assert mock_run.call_count == 1

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_missing_lock_is_noop(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Already-removed lock refs are not lifecycle failures."""
        mock_run.return_value = _gh_result(stderr="Not Found (HTTP 404)", returncode=1)

        manager.remove_non_sticky_lock("dev")

        assert mock_run.call_count == 1

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_non_sticky_lock_delete_failure_raises(
        self, mock_run: MagicMock, manager: LifecycleManager
    ) -> None:
        """A known non-sticky lock must not be silently left behind."""
        mock_run.side_effect = [
            _gh_result(stdout=_encoded_lock_metadata("false")),
            _gh_result(stderr="delete failed", returncode=1),
        ]

        with pytest.raises(RuntimeError, match="Failed to remove non-sticky lock"):
            manager.remove_non_sticky_lock("dev")

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_invalid_lock_metadata_raises(
        self, mock_run: MagicMock, manager: LifecycleManager
    ) -> None:
        """Malformed lock metadata should not be treated as sticky."""
        mock_run.return_value = _gh_result(stdout="not-base64")

        with pytest.raises(RuntimeError, match="Failed to parse lock metadata"):
            manager.remove_non_sticky_lock("dev")

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_lock_cleanup_uses_gh_host_for_ghe(
        self, mock_run: MagicMock, manager: LifecycleManager
    ) -> None:
        """Lock GET and DELETE calls must remain GitHub Enterprise compatible."""
        mock_run.side_effect = [
            _gh_result(stdout=_encoded_lock_metadata("false")),
            _gh_result(),
        ]

        with patch.dict(os.environ, {"GITHUB_SERVER_URL": "https://git.i.company.com"}):
            manager.remove_non_sticky_lock("dev")

        for call in mock_run.call_args_list:
            call_env = call[1]["env"]
            assert call_env["GH_HOST"] == "git.i.company.com"
            assert call_env["GH_ENTERPRISE_TOKEN"] == "test-token"

    def test_format_result_comment_success(self, manager: LifecycleManager) -> None:
        """Test formatting success comment."""
        env_vars = {
            "TF_BD_ACTOR": "user",
            "TF_BD_REF": "main",
            "TF_BD_ENVIRONMENT": "prod",
            "TF_BD_SHA": "abc1234",
            "TF_BD_NOOP": "false",
        }

        body = manager.format_result_comment("success", env_vars)

        assert "Deployment Results ✅" in body
        assert "**user** successfully deployed branch `main` to **prod**" in body
        assert "Details" in body
        assert '"ref": "main"' in body

    def test_format_result_comment_failure(self, manager: LifecycleManager) -> None:
        """Test formatting failure comment."""
        env_vars = {
            "TF_BD_ACTOR": "user",
            "TF_BD_REF": "feature",
            "TF_BD_ENVIRONMENT": "dev",
        }

        body = manager.format_result_comment("failure", env_vars, failure_reason="Terraform failed")

        assert "⚠️ Cannot proceed with deployment" in body
        assert "Terraform failed" in body

    def test_format_result_comment_noop(self, manager: LifecycleManager) -> None:
        """Test formatting noop success comment."""
        env_vars = {
            "TF_BD_ACTOR": "user",
            "TF_BD_REF": "main",
            "TF_BD_ENVIRONMENT": "prod",
            "TF_BD_NOOP": "true",
        }

        body = manager.format_result_comment("success", env_vars)

        assert "**noop** deployed" in body

    # GHE Support Tests

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_run_gh_sets_all_token_variants(
        self, mock_run: MagicMock, manager: LifecycleManager
    ) -> None:
        """Test that all token variants are set for maximum GHE compatibility."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        with patch.dict(os.environ, {}, clear=True):
            manager._run_gh(["gh", "version"])

        call_env = mock_run.call_args[1]["env"]
        # All three token variants should be set
        assert call_env["GITHUB_TOKEN"] == "test-token"
        assert call_env["GH_TOKEN"] == "test-token"
        assert call_env["GH_ENTERPRISE_TOKEN"] == "test-token"

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_run_gh_sets_gh_host_for_ghe(
        self, mock_run: MagicMock, manager: LifecycleManager
    ) -> None:
        """Test that GH_HOST is set from GITHUB_SERVER_URL for self-hosted GHE."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        ghe_env = {"GITHUB_SERVER_URL": "https://git.i.company.com"}

        with patch.dict(os.environ, ghe_env, clear=True):
            manager._run_gh(["gh", "api", "repos/org/repo/issues"])

        call_env = mock_run.call_args[1]["env"]
        assert call_env["GH_HOST"] == "git.i.company.com"

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_run_gh_does_not_set_gh_host_for_github_com(
        self, mock_run: MagicMock, manager: LifecycleManager
    ) -> None:
        """Test that GH_HOST is NOT set for github.com."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        env = {"GITHUB_SERVER_URL": "https://github.com"}

        with patch.dict(os.environ, env, clear=True):
            manager._run_gh(["gh", "api", "repos/org/repo/issues"])

        call_env = mock_run.call_args[1]["env"]
        assert "GH_HOST" not in call_env
