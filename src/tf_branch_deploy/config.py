"""
Configuration models using Pydantic.

This module defines the configuration schema for .tf-branch-deploy.yml
using Pydantic models. These models serve as:
1. The source of truth for configuration structure
2. Runtime validation with clear error messages
3. JSON schema generation for IDE support
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

if TYPE_CHECKING:
    from pathlib import Path


class ArgsConfig(BaseModel):
    """Configuration for command-line arguments (plan-args, apply-args, init-args)."""

    model_config = ConfigDict(extra="forbid")

    inherit: bool = True
    args: list[str] = Field(default_factory=list)

    @field_validator("args", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)


class PathsConfig(BaseModel):
    """Configuration for file paths (var-files, backend-configs)."""

    model_config = ConfigDict(extra="forbid")

    inherit: bool = True
    paths: list[str] = Field(default_factory=list)

    @field_validator("paths", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return list(v)


class DefaultsConfig(BaseModel):
    """Default configuration inherited by all environments."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    var_files: PathsConfig | None = Field(default=None, alias="var-files")
    backend_configs: PathsConfig | None = Field(default=None, alias="backend-configs")
    plan_args: ArgsConfig | None = Field(default=None, alias="plan-args")
    apply_args: ArgsConfig | None = Field(default=None, alias="apply-args")
    init_args: ArgsConfig | None = Field(default=None, alias="init-args")


class HotfixSafetyConfig(BaseModel):
    """Safety configuration for hotfix workflows."""

    model_config = ConfigDict(extra="forbid")

    require_confirmation: bool = True
    confirmation_command: str = ".confirm-hotfix"
    require_approval: bool = True
    require_ci_pass: bool = True


class HotfixDetectionConfig(BaseModel):
    """Configuration for detecting hotfix PRs."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    branch_pattern: str = Field(default="hotfix/*", alias="branch-pattern")
    targets_stable_branch: bool = Field(default=True, alias="targets-stable-branch")


class HotfixConfig(BaseModel):
    """Configuration for hotfix workflow handling."""

    model_config = ConfigDict(extra="forbid")

    detection: HotfixDetectionConfig = Field(default_factory=HotfixDetectionConfig)
    safety: HotfixSafetyConfig = Field(default_factory=HotfixSafetyConfig)


class EnvironmentConfig(BaseModel):
    """Configuration for a single deployment environment."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    working_directory: str = Field(default=".", alias="working-directory")
    var_files: PathsConfig | None = Field(default=None, alias="var-files")
    backend_configs: PathsConfig | None = Field(default=None, alias="backend-configs")
    plan_args: ArgsConfig | None = Field(default=None, alias="plan-args")
    apply_args: ArgsConfig | None = Field(default=None, alias="apply-args")
    init_args: ArgsConfig | None = Field(default=None, alias="init-args")


class TerraformBranchDeployConfig(BaseModel):
    """
    Root configuration schema for .tf-branch-deploy.yml.

    This model validates the entire configuration file and provides
    type-safe access to all configuration options.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    # Required fields
    default_environment: str = Field(..., alias="default-environment")
    production_environments: list[str] = Field(..., alias="production-environments")
    environments: dict[str, EnvironmentConfig]

    # Optional fields
    defaults: DefaultsConfig | None = None
    hotfix: HotfixConfig | None = None
    stable_branch: str = Field(default="main", alias="stable-branch")

    @field_validator("production_environments", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return list(v)

    @model_validator(mode="after")
    def validate_environment_references(self) -> TerraformBranchDeployConfig:
        """Ensure all referenced environments exist."""
        env_names = set(self.environments.keys())

        # Validate default-environment exists
        if self.default_environment not in env_names:
            raise ValueError(
                f"default-environment '{self.default_environment}' is not defined in environments. "
                f"Available environments: {sorted(env_names)}"
            )

        # Validate production-environments exist
        for prod_env in self.production_environments:
            if prod_env not in env_names:
                raise ValueError(
                    f"production-environment '{prod_env}' is not defined in environments. "
                    f"Available environments: {sorted(env_names)}"
                )

        return self

    def get_environment(self, name: str) -> EnvironmentConfig:
        """Get environment config by name, raising clear error if not found."""
        if name not in self.environments:
            raise ValueError(
                f"Environment '{name}' not found. "
                f"Available environments: {sorted(self.environments.keys())}"
            )
        return self.environments[name]

    def is_production(self, environment: str) -> bool:
        """Check if an environment is marked as production."""
        return environment in self.production_environments

    def resolve_var_files(self, environment: str) -> list[str]:
        """Resolve var-files for an environment, applying inheritance."""
        env_config = self.get_environment(environment)
        result: list[str] = []

        # Check if we should inherit from defaults
        should_inherit = True
        if env_config.var_files is not None:
            should_inherit = env_config.var_files.inherit

        # Add defaults if inheriting
        if should_inherit and self.defaults and self.defaults.var_files:
            result.extend(self.defaults.var_files.paths)

        # Add environment-specific paths
        if env_config.var_files:
            result.extend(env_config.var_files.paths)

        return result

    def resolve_backend_configs(self, environment: str) -> list[str]:
        """Resolve backend-configs for an environment, applying inheritance."""
        env_config = self.get_environment(environment)
        result: list[str] = []

        should_inherit = True
        if env_config.backend_configs is not None:
            should_inherit = env_config.backend_configs.inherit

        if should_inherit and self.defaults and self.defaults.backend_configs:
            result.extend(self.defaults.backend_configs.paths)

        if env_config.backend_configs:
            result.extend(env_config.backend_configs.paths)

        return result

    def resolve_args(
        self, environment: str, arg_type: str
    ) -> list[str]:
        """
        Resolve arguments for an environment, applying inheritance.

        Args:
            environment: The target environment name
            arg_type: One of 'plan_args', 'apply_args', 'init_args'
        """
        env_config = self.get_environment(environment)
        result: list[str] = []

        env_args = getattr(env_config, arg_type, None)
        default_args = getattr(self.defaults, arg_type, None) if self.defaults else None

        should_inherit = True
        if env_args is not None:
            should_inherit = env_args.inherit

        if should_inherit and default_args:
            result.extend(default_args.args)

        if env_args:
            result.extend(env_args.args)

        return result


def load_config(config_path: Path) -> TerraformBranchDeployConfig:
    """
    Load and validate configuration from a YAML file.

    Args:
        config_path: Path to .tf-branch-deploy.yml

    Returns:
        Validated configuration object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path) as f:
        raw_config = yaml.safe_load(f)

    if not raw_config:
        raise ValueError(f"Configuration file is empty: {config_path}")

    return TerraformBranchDeployConfig.model_validate(raw_config)


def generate_json_schema() -> dict[str, Any]:
    """Generate JSON schema for IDE validation support."""
    return TerraformBranchDeployConfig.model_json_schema(by_alias=True)
