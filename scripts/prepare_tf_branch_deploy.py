#!/usr/bin/env python3


import sys
import os
import yaml
import shlex
from pathlib import Path
from typing import Any, Dict, List

# --- Constants ---
CONFIG_FILE_NAME = ".tf-branch-deploy.yml"


# --- Logging Helpers ---
def log_debug(msg: str) -> None:
    """
    Logs a debug-level message.
    These messages are only visible in the Actions UI when debug logging is enabled.
    Args:
        msg (str): The debug message to log.
    """
    print(f"::debug::{msg}")


def log_info(msg: str) -> None:
    """
    Logs an informational message.
    Args:
        msg (str): The info message to log (should use emoji description: value format).
    """
    print(msg)


def log_warning(msg: str) -> None:
    """
    Logs a warning-level message.
    Args:
        msg (str): The warning message to log.
    """
    print(f"::warning::{msg}")


def log_section(title: str) -> None:
    """Prints a formatted section header to the logs."""
    print(f"\n{title}\n{'-' * len(title)}")


def error_exit(message: str) -> None:
    """
    Prints a GitHub Actions-formatted error message and exits the script.
    Args:
        message (str): The error message to log and print.
    """
    print(f"::error::{message}")
    sys.exit(1)


def process_args(
    config: Dict[str, Any], env_name: str, key_name: str, arg_prefix: str
) -> List[str]:
    """
    Processes a list of arguments (e.g., plan-args, apply-args), handling inheritance
    from defaults and validating input types.
    Args:
        config (Dict[str, Any]): The loaded YAML configuration.
        env_name (str): The environment name (e.g., 'dev', 'prod').
        key_name (str): The key to process (e.g., 'plan-args', 'apply-args', 'init-args').
        arg_prefix (str): Prefix to prepend to each argument (e.g., '', '-backend-config=').
    Returns:
        List[str]: The processed argument list.
    """
    final_args: List[str] = []

    inherit: bool = (
        config.get("environments", {})
        .get(env_name, {})
        .get(key_name, {})
        .get("inherit", True)
    )
    log_debug(
        f"Processing '{key_name}' for environment '{env_name}'. Inherit: {inherit}"
    )

    if inherit:
        default_items = config.get("defaults", {}).get(key_name, {}).get("args", [])
        if not isinstance(default_items, list):
            error_exit(
                f"Configuration Error: '.defaults.{key_name}.args' must be a list."
            )
        for item in default_items:
            if not isinstance(item, str):
                error_exit(
                    f"Configuration Error: Argument '{item}' in '.defaults.{key_name}.args' must be a string."
                )
            final_args.append(f"{arg_prefix}{item}")
        log_debug(f"Inherited default '{key_name}' args: {final_args}")

    env_items = (
        config.get("environments", {})
        .get(env_name, {})
        .get(key_name, {})
        .get("args", [])
    )
    if not isinstance(env_items, list):
        error_exit(
            f"Configuration Error: '.environments.{env_name}.{key_name}.args' must be a list."
        )
    for item in env_items:
        if not isinstance(item, str):
            error_exit(
                f"Configuration Error: Argument '{item}' in '.environments.{env_name}.{key_name}.args' must be a string."
            )
        final_args.append(f"{arg_prefix}{item}")
    log_debug(f"Environment-specific '{key_name}' args: {env_items}")

    return final_args


def get_relative_path_for_tf(
    original_path_from_config: str, base_repo_path: Path, tf_working_dir_absolute: Path
) -> str:
    """
        Resolves a file path for Terraform CLI arguments (e.g., -var-file, -backend-config) to ensure it is valid
        when running from the Terraform working directory.
    Args:
        original_path_from_config (str): Path as specified in .tf-branch-deploy.yml (absolute or relative).
        base_repo_path (Path): Absolute path to the repository root (e.g., $GITHUB_WORKSPACE/repo_checkout).
        tf_working_dir_absolute (Path): Absolute path to the Terraform working directory.
    Returns:
        str: A path suitable for use as a Terraform CLI argument, relative to the working directory if possible,
        otherwise absolute.
    """
    p = Path(original_path_from_config)

    if p.is_absolute():
        if not p.exists():
            error_exit(
                f"Configuration Error: Absolute file path '{original_path_from_config}' does not exist."
            )
        log_debug(f"Using absolute path for Terraform: {p}")
        return str(p)

    abs_path_in_tf_working_dir = tf_working_dir_absolute / p
    if abs_path_in_tf_working_dir.exists():
        relative_path = abs_path_in_tf_working_dir.relative_to(tf_working_dir_absolute)
        log_debug(
            f"Resolved path '{original_path_from_config}' to '{relative_path}' relative to TF working dir '{tf_working_dir_absolute}' (found in working dir)"
        )
        return str(relative_path)

    abs_path_in_repo_checkout = base_repo_path / p
    if abs_path_in_repo_checkout.exists():
        try:
            relative_path = abs_path_in_repo_checkout.relative_to(
                tf_working_dir_absolute
            )
            log_debug(
                f"Resolved path '{original_path_from_config}' to '{relative_path}' relative to TF working dir '{tf_working_dir_absolute}' (found in repo root, relative to working dir)"
            )
            return str(relative_path)
        except ValueError:
            log_warning(
                f"Path '{original_path_from_config}' is not under Terraform working directory '{tf_working_dir_absolute}'. Using absolute path."
            )
            return str(abs_path_in_repo_checkout)

    error_exit(
        f"Configuration Error: File '{original_path_from_config}' specified in .tf-branch-deploy.yml not found relative to working directory or repository root."
    )


def validate_inputs(argv: list[str]) -> tuple[str, str, str]:
    """
    Validates and parses command-line arguments for the script.
    Args:
        argv (list[str]): List of command-line arguments.
    Returns:
        tuple[str, str, str]: default_working_dir, env_name, dynamic_params_str
    """
    if len(argv) != 4:
        error_exit(
            f"Usage: {argv[0]} <default_working_dir> <env_name> <dynamic_params_str>"
        )
    default_working_dir: str = argv[1]
    env_name: str = argv[2]
    dynamic_params_str: str = argv[3]

    log_debug(f"Script received default_working_dir: '{default_working_dir}'")
    log_debug(f"Script received env_name: '{env_name}'")
    log_debug(f"Script received dynamic_params_str: '{dynamic_params_str}'")

    if not isinstance(default_working_dir, str) or not default_working_dir.strip():
        error_exit("Invalid or empty working directory argument provided to script.")
    if not isinstance(env_name, str) or not env_name.strip():
        error_exit("Invalid or empty environment name argument provided to script.")
    if not isinstance(dynamic_params_str, str):
        error_exit("Invalid dynamic_params_str argument provided to script.")
    return default_working_dir, env_name, dynamic_params_str


def validate_github_output() -> str:
    """
    Validates the GITHUB_OUTPUT environment variable and its parent directory.
    Returns:
        str: The output file path.
    """
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        error_exit("GITHUB_OUTPUT environment variable not set. Cannot write outputs.")
    if not Path(output_path).parent.exists():
        error_exit(
            f"Parent directory for GITHUB_OUTPUT ('{Path(output_path).parent}') does not exist or is not accessible."
        )
    return output_path


def load_config(
    original_repo_root_path: Path,
    env_name: str,
    config_file_name: str = CONFIG_FILE_NAME,
) -> tuple[dict, dict]:
    """
    Loads the YAML configuration file and validates the environments section.
    Args:
        original_repo_root_path (Path): Path to the repository root.
        env_name (str): The environment name.
        config_file_name (str): The config file name.
    Returns:
        tuple[dict, dict]: The loaded config and environments dict.
    """
    config_path = original_repo_root_path / config_file_name
    config: Dict[str, Any] = {}
    if config_path.is_file():
        log_info(f"✅ Found {config_file_name}: {config_path}")
        log_info(f"🌍 Environment: {env_name}")
        with open(config_path, "r") as f:
            try:
                config = yaml.safe_load(f) or {}
                log_debug(f"Loaded config: {config}")
            except yaml.YAMLError as e:
                error_exit(f"Error parsing {config_file_name}: {e}")

        environments = config.get("environments", {})
        if not isinstance(environments, dict) or not environments:
            error_exit(
                f"Configuration Error: 'environments' section is missing or empty in '{config_file_name}'. At least one environment must be defined."
            )
    else:
        log_info(
            f"⚠️ No {config_file_name} found: {config_path}. Using action defaults and assuming 'production' environment configuration."
        )
        environments = {"production": {}}
        config["environments"] = environments
    return config, environments


def validate_environment(
    env_name: str, environments: dict, config_file_name: str = CONFIG_FILE_NAME
) -> None:
    """
    Validates that the requested environment exists in the configuration.
    Args:
        env_name (str): The environment name.
        environments (dict): The environments section from config.
        config_file_name (str): The config file name.
    """
    if env_name and env_name != "production" and env_name not in environments:
        error_exit(
            f"Configuration Error: Environment '{env_name}' not found in '{config_file_name}'."
        )


def resolve_working_dir(
    config: dict,
    env_name: str,
    default_working_dir: str,
    base_repo_path_for_tf_code: Path,
    config_file_name: str = CONFIG_FILE_NAME,
) -> tuple[str, Path]:
    """
    Determines the effective Terraform working directory based on config and environment.
    Args:
        config (dict): The loaded configuration.
        env_name (str): The environment name.
        default_working_dir (str): The default working directory.
        base_repo_path_for_tf_code (Path): The repo root for TF code.
        config_file_name (str): The config file name.
    Returns:
        tuple[str, Path]: The effective working dir (relative) and its absolute Path.
    """
    config_working_dir_rel_to_repo_root: str = (
        config.get("environments", {})
        .get(env_name, {})
        .get("working-directory", default_working_dir)
    )

    if config_working_dir_rel_to_repo_root.startswith("./"):
        config_working_dir_rel_to_repo_root = config_working_dir_rel_to_repo_root[2:]

    if config_working_dir_rel_to_repo_root == ".":
        config_working_dir_rel_to_repo_root = ""

    tf_module_absolute_path = (
        base_repo_path_for_tf_code / config_working_dir_rel_to_repo_root
    )

    if not tf_module_absolute_path.is_dir():
        error_exit(
            f"Terraform working directory '{config_working_dir_rel_to_repo_root}' (resolved to '{tf_module_absolute_path}') not found or is not a directory. Please check 'working-directory' in '{config_file_name}'."
        )

    effective_working_dir_for_output = config_working_dir_rel_to_repo_root
    log_info(
        f"📁 Terraform Working Directory (relative to repo_checkout): {effective_working_dir_for_output}"
    )
    return effective_working_dir_for_output, tf_module_absolute_path


def build_init_args(
    config: dict,
    env_name: str,
    original_repo_root_path: Path,
    tf_module_absolute_path: Path,
) -> list[str]:
    """
    Builds the list of Terraform init arguments, including backend configs.
    Args:
        config (dict): The loaded configuration.
        env_name (str): The environment name.
        original_repo_root_path (Path): The repo root.
        tf_module_absolute_path (Path): The TF working directory.
    Returns:
        list[str]: The list of init arguments.
    """
    init_args_list: List[str] = []
    backend_configs_section = (
        config.get("environments", {}).get(env_name, {}).get("backend-configs", {})
    )
    if backend_configs_section.get("inherit", True):
        default_backend_paths = (
            config.get("defaults", {}).get("backend-configs", {}).get("paths", [])
        )
        if not isinstance(default_backend_paths, list):
            error_exit(
                "Configuration Error: '.defaults.backend-configs.paths' must be a list."
            )
        for path_item in default_backend_paths:
            if not isinstance(path_item, str):
                error_exit(
                    f"Configuration Error: Path '{path_item}' in '.defaults.backend-configs.paths' must be a string."
                )
            relative_tf_path = get_relative_path_for_tf(
                path_item, original_repo_root_path, tf_module_absolute_path
            )
            init_args_list.append(f"-backend-config={relative_tf_path}")

    env_backend_paths = backend_configs_section.get("paths", [])
    if not isinstance(env_backend_paths, list):
        error_exit(
            f"Configuration Error: '.environments.{env_name}.backend-configs.paths' must be a list."
        )
    for path_item in env_backend_paths:
        if not isinstance(path_item, str):
            error_exit(
                f"Configuration Error: Path '{path_item}' in '.environments.{env_name}.backend-configs.paths' must be a string."
            )
        relative_tf_path = get_relative_path_for_tf(
            path_item, original_repo_root_path, tf_module_absolute_path
        )
        init_args_list.append(f"-backend-config={relative_tf_path}")
    log_debug(f"Collected init backend-configs: {init_args_list}")

    init_args_list.extend(process_args(config, env_name, "init-args", ""))
    log_debug(f"Collected all init args: {init_args_list}")
    return init_args_list


def build_plan_args(
    config: dict,
    env_name: str,
    original_repo_root_path: Path,
    tf_module_absolute_path: Path,
) -> list[str]:
    """
    Builds the list of Terraform plan arguments, including var-files.
    Args:
        config (dict): The loaded configuration.
        env_name (str): The environment name.
        original_repo_root_path (Path): The repo root.
        tf_module_absolute_path (Path): The TF working directory.
    Returns:
        list[str]: The list of plan arguments.
    """
    plan_args_list: List[str] = []
    var_files_section = (
        config.get("environments", {}).get(env_name, {}).get("var-files", {})
    )
    if var_files_section.get("inherit", True):
        default_var_paths = (
            config.get("defaults", {}).get("var-files", {}).get("paths", [])
        )
        if not isinstance(default_var_paths, list):
            error_exit(
                "Configuration Error: '.defaults.var-files.paths' must be a list."
            )
        for path_item in default_var_paths:
            if not isinstance(path_item, str):
                error_exit(
                    f"Configuration Error: Path '{path_item}' in '.defaults.var-files.paths' must be a string."
                )
            relative_tf_path = get_relative_path_for_tf(
                path_item, original_repo_root_path, tf_module_absolute_path
            )
            plan_args_list.append(f"-var-file={relative_tf_path}")

    env_var_paths = var_files_section.get("paths", [])
    if not isinstance(env_var_paths, list):
        error_exit(
            f"Configuration Error: '.environments.{env_name}.var-files.paths' must be a list."
        )
    for path_item in env_var_paths:
        if not isinstance(path_item, str):
            error_exit(
                f"Configuration Error: Path '{path_item}' in '.environments.{env_name}.var-files.paths' must be a string."
            )
        relative_tf_path = get_relative_path_for_tf(
            path_item, original_repo_root_path, tf_module_absolute_path
        )
        plan_args_list.append(f"-var-file={relative_tf_path}")
    log_debug(f"Collected plan var-files: {plan_args_list}")

    plan_args_list.extend(process_args(config, env_name, "plan-args", ""))
    log_debug(f"Collected all plan args: {plan_args_list}")
    return plan_args_list


def build_apply_args(config: dict, env_name: str) -> list[str]:
    """
    Builds the list of Terraform apply arguments.
    Args:
        config (dict): The loaded configuration.
        env_name (str): The environment name.
    Returns:
        list[str]: The list of apply arguments.
    """
    apply_args_list: List[str] = []
    apply_args_list.extend(process_args(config, env_name, "apply-args", ""))
    log_debug(f"Collected all apply args: {apply_args_list}")
    return apply_args_list


def parse_dynamic_flags(dynamic_params_str: str) -> list[str]:
    """
    Parses and sanitizes dynamic flags from the input string.
    Args:
        dynamic_params_str (str): The dynamic parameters string.
    Returns:
        list[str]: The list of allowed dynamic flags.
    """
    allowed_dynamic_flags_prefixes: List[str] = [
        "--target=",
        "-target=",
        "-var=",
        "--var=",
    ]
    dynamic_flags: List[str] = []

    parsed_params = shlex.split(dynamic_params_str)
    log_debug(f"Parsed dynamic params from comment: {parsed_params}")

    for param in parsed_params:
        is_allowed = False
        for allowed_prefix in allowed_dynamic_flags_prefixes:
            if param.startswith(allowed_prefix):
                is_allowed = True
                break

        if is_allowed:
            dynamic_flags.append(param)
        else:
            log_warning(
                f"Ignoring potentially malicious or unsupported dynamic flag from comment: '{param}'. Only flags starting with '{', '.join(allowed_dynamic_flags_prefixes)}' are allowed."
            )
    return dynamic_flags


def write_outputs(
    output_path: str,
    effective_working_dir_for_output: str,
    final_init_args_str: str,
    final_plan_args_str: str,
    final_apply_args_str: str,
) -> None:
    """
    Writes the prepared outputs to the GITHUB_OUTPUT file.
    Args:
        output_path (str): The output file path.
        effective_working_dir_for_output (str): The working directory.
        final_init_args_str (str): The init args string.
        final_plan_args_str (str): The plan args string.
        final_apply_args_str (str): The apply args string.
    """
    try:
        with open(output_path, "a") as f:
            f.write(f"working_dir={effective_working_dir_for_output}\n")
            f.write(f"init_args={final_init_args_str}\n")
            f.write(f"plan_args={final_plan_args_str}\n")
            f.write(f"apply_args={final_apply_args_str}\n")
        log_debug(f"Successfully wrote outputs to GITHUB_OUTPUT: {output_path}")
    except Exception as e:
        error_exit(f"Failed to write to GITHUB_OUTPUT file '{output_path}': {e}")


def print_summary(
    effective_working_dir_for_output: str,
    final_init_args_str: str,
    final_plan_args_str: str,
    final_apply_args_str: str,
) -> None:
    """
    Prints a summary of the prepared configuration to the logs.
    Args:
        effective_working_dir_for_output (str): The working directory.
        final_init_args_str (str): The init args string.
        final_plan_args_str (str): The plan args string.
        final_apply_args_str (str): The apply args string.
    """
    log_section("📝 terraform-branch-deploy configuration summary:")
    log_info(
        f"📁 Terraform Working Directory (relative to repo_checkout): {effective_working_dir_for_output}"
    )
    log_info(f"🏗️ Terraform Init Arguments: {final_init_args_str}")
    log_info(f"📋 Terraform Plan Arguments: {final_plan_args_str}")
    log_info(f"🚀 Terraform Apply Arguments: {final_apply_args_str}")
    log_info("✅ Configuration prepared for Terraform execution.")


def main() -> None:
    """
    Entry point for the script. Validates inputs, loads configuration, prepares arguments,
    writes outputs for GitHub Actions, and prints a summary for the user.
    """
    default_working_dir, env_name, dynamic_params_str = validate_inputs(sys.argv)
    output_path = validate_github_output()
    base_repo_path_for_tf_code = Path(os.getcwd())
    log_debug(
        f"Script executing from base_repo_path_for_tf_code (repo_checkout): {base_repo_path_for_tf_code}"
    )
    # Use the current working directory (user-repo) for config file location
    original_repo_root_path = base_repo_path_for_tf_code
    log_debug(f"Repository root for config file: {original_repo_root_path}")

    config, environments = load_config(original_repo_root_path, env_name)
    validate_environment(env_name, environments)
    effective_working_dir_for_output, tf_module_absolute_path = resolve_working_dir(
        config, env_name, default_working_dir, base_repo_path_for_tf_code
    )

    init_args_list = build_init_args(
        config, env_name, original_repo_root_path, tf_module_absolute_path
    )
    plan_args_list = build_plan_args(
        config, env_name, original_repo_root_path, tf_module_absolute_path
    )
    apply_args_list = build_apply_args(config, env_name)

    dynamic_flags = parse_dynamic_flags(dynamic_params_str)
    plan_args_list.extend(dynamic_flags)

    final_init_args_str: str = " ".join(shlex.quote(arg) for arg in init_args_list)
    final_plan_args_str: str = " ".join(shlex.quote(arg) for arg in plan_args_list)
    final_apply_args_str: str = " ".join(shlex.quote(arg) for arg in apply_args_list)

    write_outputs(
        output_path,
        effective_working_dir_for_output,
        final_init_args_str,
        final_plan_args_str,
        final_apply_args_str,
    )
    print_summary(
        effective_working_dir_for_output,
        final_init_args_str,
        final_plan_args_str,
        final_apply_args_str,
    )


if __name__ == "__main__":
    main()
