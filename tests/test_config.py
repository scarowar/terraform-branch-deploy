"""Tests for configuration module."""

from pathlib import Path
from textwrap import dedent

import pytest

from tf_branch_deploy.config import (
    TerraformBranchDeployConfig,
    generate_json_schema,
    load_config,
)


class TestTerraformBranchDeployConfig:
    """Tests for the main configuration model."""

    def test_minimal_valid_config(self) -> None:
        """Test that minimal required config is valid."""
        config = TerraformBranchDeployConfig.model_validate(
            {
                "default-environment": "dev",
                "production-environments": ["prod"],
                "environments": {
                    "dev": {},
                    "prod": {},
                },
            }
        )

        assert config.default_environment == "dev"
        assert config.production_environments == ["prod"]
        assert "dev" in config.environments
        assert "prod" in config.environments

    def test_default_environment_must_exist(self) -> None:
        """Test that default-environment must reference an existing environment."""
        with pytest.raises(ValueError, match="not defined in environments"):
            TerraformBranchDeployConfig.model_validate(
                {
                    "default-environment": "staging",  # Doesn't exist
                    "production-environments": ["prod"],
                    "environments": {
                        "dev": {},
                        "prod": {},
                    },
                }
            )

    def test_production_environment_must_exist(self) -> None:
        """Test that production-environments must reference existing environments."""
        with pytest.raises(ValueError, match="not defined in environments"):
            TerraformBranchDeployConfig.model_validate(
                {
                    "default-environment": "dev",
                    "production-environments": ["prod", "staging"],  # staging doesn't exist
                    "environments": {
                        "dev": {},
                        "prod": {},
                    },
                }
            )

    def test_is_production(self) -> None:
        """Test production environment detection."""
        config = TerraformBranchDeployConfig.model_validate(
            {
                "default-environment": "dev",
                "production-environments": ["prod", "prod-eu"],
                "environments": {
                    "dev": {},
                    "prod": {},
                    "prod-eu": {},
                },
            }
        )

        assert not config.is_production("dev")
        assert config.is_production("prod")
        assert config.is_production("prod-eu")

    def test_var_files_inheritance(self) -> None:
        """Test that var-files properly inherit from defaults."""
        config = TerraformBranchDeployConfig.model_validate(
            {
                "default-environment": "dev",
                "production-environments": ["prod"],
                "defaults": {"var-files": {"paths": ["common.tfvars"]}},
                "environments": {
                    "dev": {"var-files": {"paths": ["dev.tfvars"]}},
                    "prod": {"var-files": {"inherit": False, "paths": ["prod.tfvars"]}},
                },
            }
        )

        # dev inherits common.tfvars
        dev_var_files = config.resolve_var_files("dev")
        assert dev_var_files == ["common.tfvars", "dev.tfvars"]

        # prod does NOT inherit
        prod_var_files = config.resolve_var_files("prod")
        assert prod_var_files == ["prod.tfvars"]

    def test_args_inheritance(self) -> None:
        """Test that args properly inherit from defaults."""
        config = TerraformBranchDeployConfig.model_validate(
            {
                "default-environment": "dev",
                "production-environments": ["prod"],
                "defaults": {"plan-args": {"args": ["-compact-warnings"]}},
                "environments": {
                    "dev": {},
                    "prod": {"plan-args": {"inherit": False, "args": ["-parallelism=30"]}},
                },
            }
        )

        # dev inherits defaults
        dev_plan_args = config.resolve_args("dev", "plan_args")
        assert dev_plan_args == ["-compact-warnings"]

        # prod overrides
        prod_plan_args = config.resolve_args("prod", "plan_args")
        assert prod_plan_args == ["-parallelism=30"]

    def test_working_directory_default(self) -> None:
        """Test that working-directory defaults to current directory."""
        config = TerraformBranchDeployConfig.model_validate(
            {
                "default-environment": "dev",
                "production-environments": ["dev"],
                "environments": {
                    "dev": {},  # No working-directory specified
                },
            }
        )

        env = config.get_environment("dev")
        assert env.working_directory == "."

    def test_extra_fields_rejected(self) -> None:
        """Test that unknown fields are rejected."""
        with pytest.raises(ValueError, match="Extra inputs are not permitted"):
            TerraformBranchDeployConfig.model_validate(
                {
                    "default-environment": "dev",
                    "production-environments": ["dev"],
                    "environments": {"dev": {}},
                    "unknown_field": "value",
                }
            )


class TestLoadConfig:
    """Tests for the load_config function."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Test proper error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Configuration file not found"):
            load_config(tmp_path / "nonexistent.yml")

    def test_empty_file(self, tmp_path: Path) -> None:
        """Test proper error when config file is empty."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text("")

        with pytest.raises(ValueError, match="Configuration file is empty"):
            load_config(config_file)

    def test_valid_yaml_file(self, tmp_path: Path) -> None:
        """Test loading a valid YAML config file."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            dedent("""
            default-environment: dev
            production-environments:
              - prod
            environments:
              dev:
                working-directory: ./terraform/dev
              prod:
                working-directory: ./terraform/prod
        """)
        )

        config = load_config(config_file)

        assert config.default_environment == "dev"
        assert config.get_environment("dev").working_directory == "./terraform/dev"


class TestJsonSchema:
    """Tests for JSON schema generation."""

    def test_schema_generation(self) -> None:
        """Test that JSON schema is generated correctly."""
        schema = generate_json_schema()

        assert schema["type"] == "object"
        assert "properties" in schema
        # Check key properties exist with correct aliases
        props = schema["properties"]
        assert "default-environment" in props
        assert "production-environments" in props
        assert "environments" in props
