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
        return LifecycleManager(repo="org/repo", github_token="token")

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

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_run_gh_injects_gh_host(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test that GH_HOST is injected derived from GITHUB_SERVER_URL."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # Mock environment with GHE URL
        ghe_env = {
            "GITHUB_SERVER_URL": "https://github.enterprise.com",
        }
        # Ensure GH_HOST is NOT set initially
        if "GH_HOST" in os.environ:
            del os.environ["GH_HOST"]

        with patch.dict(os.environ, ghe_env, clear=True):
            manager._run_gh(["gh", "version"])

        mock_run.assert_called_once()
        call_env = mock_run.call_args[1]["env"]
        
        assert call_env["GH_HOST"] == "github.enterprise.com"

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_run_gh_respects_existing_gh_host(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test that existing GH_HOST is respected."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        env_vars = {
            "GITHUB_SERVER_URL": "https://github.enterprise.com",
            "GH_HOST": "custom.host.com"
        }

        with patch.dict(os.environ, env_vars, clear=True):
            manager._run_gh(["gh", "version"])

        call_env = mock_run.call_args[1]["env"]
        assert call_env["GH_HOST"] == "custom.host.com"

    @patch("tf_branch_deploy.lifecycle.subprocess.run")
    def test_run_gh_ignores_github_com(self, mock_run: MagicMock, manager: LifecycleManager) -> None:
        """Test that we don't set GH_HOST for standard github.com."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        env_vars = {
            "GITHUB_SERVER_URL": "https://github.com"
        }

        with patch.dict(os.environ, env_vars, clear=True):
            manager._run_gh(["gh", "version"])

        call_env = mock_run.call_args[1]["env"]
        assert "GH_HOST" not in call_env
