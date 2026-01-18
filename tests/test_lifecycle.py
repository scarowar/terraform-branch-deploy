"""Tests for lifecycle module."""

import os

from unittest.mock import MagicMock, patch

import pytest

from tf_branch_deploy.lifecycle import LifecycleManager


class TestLifecycleManager:
    """Tests for LifecycleManager."""

    @pytest.fixture
    def manager(self) -> LifecycleManager:
        """Create a LifecycleManager instance."""
        return LifecycleManager(repo="org/repo", github_token="test-token")

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_update_deployment_status(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test updating deployment status."""
        manager.update_deployment_status("123", "success", "prod")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        args_str = " ".join(args)
        assert "gh" in args_str
        assert "deployments/123/statuses" in args_str
        assert "state=success" in args_str

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_remove_reaction(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test removing reaction."""
        manager.remove_reaction("456", "789")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        args_str = " ".join(args)
        assert "DELETE" in args_str
        assert "issues/comments/456/reactions/789" in args_str

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_add_reaction(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test adding reaction."""
        manager.add_reaction("456", "rocket")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        args_str = " ".join(args)
        assert "POST" in args_str
        assert "issues/comments/456/reactions" in args_str
        assert "content=rocket" in args_str

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_post_result_comment(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test posting result comment."""
        manager.post_result_comment("100", "body")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        args_str = " ".join(args)
        assert "issues/100/comments" in args_str
        assert "body=body" in args_str

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
