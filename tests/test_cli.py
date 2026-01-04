"""Tests for CLI module."""

from pathlib import Path
from textwrap import dedent

from typer.testing import CliRunner

from tf_branch_deploy.cli import app

runner = CliRunner()


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_config(self, tmp_path: Path) -> None:
        """Test validating a correct config file."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(dedent("""
            default-environment: dev
            production-environments:
              - prod
            environments:
              dev:
                working-directory: ./terraform/dev
              prod:
                working-directory: ./terraform/prod
        """))

        result = runner.invoke(app, ["validate", "--config", str(config_file)])

        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    def test_validate_missing_config(self, tmp_path: Path) -> None:
        """Test error when config file doesn't exist."""
        result = runner.invoke(app, ["validate", "--config", str(tmp_path / "missing.yml")])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_validate_invalid_config(self, tmp_path: Path) -> None:
        """Test error for invalid config."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(dedent("""
            # Missing required fields
            environments:
              dev: {}
        """))

        result = runner.invoke(app, ["validate", "--config", str(config_file)])

        assert result.exit_code == 1


class TestEnvironmentsCommand:
    """Tests for the environments command."""

    def test_list_environments(self, tmp_path: Path) -> None:
        """Test listing environments from config."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(dedent("""
            default-environment: dev
            production-environments: [prod]
            environments:
              dev: {}
              staging: {}
              prod: {}
        """))

        result = runner.invoke(app, ["environments", "--config", str(config_file)])

        assert result.exit_code == 0
        # Should contain all environments
        assert "dev" in result.stdout
        assert "staging" in result.stdout
        assert "prod" in result.stdout


class TestRunCommand:
    """Tests for the run command."""

    def test_run_with_valid_environment(self, tmp_path: Path) -> None:
        """Test running with a valid environment."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(dedent("""
            default-environment: dev
            production-environments: [prod]
            environments:
              dev:
                working-directory: ./terraform/dev
              prod:
                working-directory: ./terraform/prod
        """))

        result = runner.invoke(app, [
            "run",
            "--environment", "dev",
            "--operation", "plan",
            "--sha", "abc123def456",
            "--config", str(config_file),
            "--mode", "skip",  # Skip mode - don't run terraform
        ])

        assert result.exit_code == 0
        assert "dev" in result.stdout

    def test_run_with_invalid_environment(self, tmp_path: Path) -> None:
        """Test error for invalid environment."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(dedent("""
            default-environment: dev
            production-environments: [dev]
            environments:
              dev: {}
        """))

        result = runner.invoke(app, [
            "run",
            "--environment", "staging",  # Doesn't exist
            "--operation", "plan",
            "--sha", "abc123",
            "--config", str(config_file),
        ])

        assert result.exit_code == 1
        # Error message should mention the environment isn't found/defined
        assert "staging" in result.stdout.lower()


class TestSchemaCommand:
    """Tests for the schema command."""

    def test_outputs_valid_json(self) -> None:
        """Test that schema command outputs valid JSON."""
        result = runner.invoke(app, ["schema"])

        assert result.exit_code == 0
        # Output should be parseable JSON
        import json
        schema = json.loads(result.stdout)
        assert "properties" in schema
