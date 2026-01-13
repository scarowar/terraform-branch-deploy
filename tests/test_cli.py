"""Tests for CLI module."""

from pathlib import Path
from textwrap import dedent

from typer.testing import CliRunner

from tf_branch_deploy.cli import (
    DEFAULT_CONFIG_PATH,
    _ArgTokenizer,
    _parse_extra_args,
    _strip_shell_quotes,
    app,
)

runner = CliRunner()


class TestConstants:
    """Tests for CLI constants."""

    def test_default_config_path_is_path(self) -> None:
        """DEFAULT_CONFIG_PATH should be a Path object."""
        assert isinstance(DEFAULT_CONFIG_PATH, Path)

    def test_default_config_path_value(self) -> None:
        """DEFAULT_CONFIG_PATH should be .tf-branch-deploy.yml."""
        assert str(DEFAULT_CONFIG_PATH) == ".tf-branch-deploy.yml"


class TestParseExtraArgs:
    """Tests for _parse_extra_args function."""

    def test_simple_args(self) -> None:
        """Test parsing simple space-separated args."""
        result = _parse_extra_args("-refresh=false -parallelism=5")
        assert result == ["-refresh=false", "-parallelism=5"]

    def test_single_quoted_value(self) -> None:
        """Test parsing single-quoted values."""
        result = _parse_extra_args("-var='msg=hello world'")
        assert result == ["-var=msg=hello world"]

    def test_double_quoted_value(self) -> None:
        """Test parsing double-quoted values."""
        result = _parse_extra_args('-var="key=value"')
        assert result == ["-var=key=value"]

    def test_bracket_with_quotes(self) -> None:
        """Test parsing terraform target with internal quotes."""
        result = _parse_extra_args('-target=module.test["key"]')
        assert result == ['-target=module.test["key"]']

    def test_mixed_args(self) -> None:
        """Test parsing mixed argument styles."""
        result = _parse_extra_args("-var='x=1' -target=module.foo -refresh=false")
        assert result == ["-var=x=1", "-target=module.foo", "-refresh=false"]

    def test_empty_string(self) -> None:
        """Test parsing empty string."""
        result = _parse_extra_args("")
        assert result == []

    def test_spaces_in_value(self) -> None:
        """Test preserving spaces within quoted values."""
        result = _parse_extra_args("-var='message=hello world foo bar'")
        assert result == ["-var=message=hello world foo bar"]


class TestStripShellQuotes:
    """Tests for _strip_shell_quotes function."""

    def test_single_quotes(self) -> None:
        """Strip single quotes from value."""
        assert _strip_shell_quotes("-var='value'") == "-var=value"

    def test_double_quotes(self) -> None:
        """Strip double quotes from value."""
        assert _strip_shell_quotes('-var="value"') == "-var=value"

    def test_no_quotes(self) -> None:
        """Leave unquoted values unchanged."""
        assert _strip_shell_quotes("-var=value") == "-var=value"

    def test_no_equals(self) -> None:
        """Arguments without = are left unchanged."""
        assert _strip_shell_quotes("-help") == "-help"

    def test_preserve_internal_quotes(self) -> None:
        """Internal quotes in terraform targets are preserved."""
        assert _strip_shell_quotes('-target=module["key"]') == '-target=module["key"]'


class TestArgTokenizer:
    """Tests for _ArgTokenizer class."""

    def test_tokenize_simple(self) -> None:
        """Tokenize simple space-separated args."""
        tokenizer = _ArgTokenizer()
        result = tokenizer.tokenize("a b c")
        assert result == ["a", "b", "c"]

    def test_tokenize_preserves_quotes(self) -> None:
        """Tokenizer preserves quotes in output."""
        tokenizer = _ArgTokenizer()
        result = tokenizer.tokenize("-var='x=1'")
        assert result == ["-var='x=1'"]

    def test_tokenize_handles_brackets(self) -> None:
        """Tokenizer handles brackets in terraform args."""
        tokenizer = _ArgTokenizer()
        result = tokenizer.tokenize('-target=module["key"] -var=x')
        assert result == ['-target=module["key"]', "-var=x"]


class TestValidateCommand:
    """Tests for the validate command."""

    def test_validate_valid_config(self, tmp_path: Path) -> None:
        """Test validating a correct config file."""
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
        config_file.write_text(
            dedent("""
            # Missing required fields
            environments:
              dev: {}
        """)
        )

        result = runner.invoke(app, ["validate", "--config", str(config_file)])

        assert result.exit_code == 1


class TestEnvironmentsCommand:
    """Tests for the environments command."""

    def test_list_environments(self, tmp_path: Path) -> None:
        """Test listing environments from config."""
        config_file = tmp_path / ".tf-branch-deploy.yml"
        config_file.write_text(
            dedent("""
            default-environment: dev
            production-environments: [prod]
            environments:
              dev: {}
              staging: {}
              prod: {}
        """)
        )

        result = runner.invoke(app, ["environments", "--config", str(config_file)])

        assert result.exit_code == 0
        # Should contain all environments
        assert "dev" in result.stdout
        assert "staging" in result.stdout
        assert "prod" in result.stdout


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
