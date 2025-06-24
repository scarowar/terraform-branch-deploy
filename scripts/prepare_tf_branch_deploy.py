#!/usr/bin/env python3

import sys
import os
import yaml
import shlex
from pathlib import Path
from typing import Any, Dict, List, Callable


# --- Logging Helpers ---
def _get_log_function(
    level: str, prefix: str, github_command: str = ""
) -> Callable[[str], None]:
    """
    Factory function to create logging functions that always print,
    but use GitHub Actions annotations for DEBUG, WARNING, and ERROR.
    """
    if level == "DEBUG":
        return lambda msg: print(f"::debug::{msg}")
    elif level == "WARNING":
        return lambda msg: print(f"::warning::{msg}")
    elif level == "ERROR":
        return lambda msg: print(f"::error::{msg}")
    else:
        return lambda msg: print(f"{prefix} {msg}")


log_debug = _get_log_function("DEBUG", "🐛 DEBUG:", "debug")
log_info = _get_log_function("INFO", "💡 INFO:")
log_warning = _get_log_function("WARNING", "⚠️ WARNING:", "warning")


def log_section(title: str) -> None:
    """Prints a formatted section header to the logs."""
    print(f"\n{title}\n{'-' * len(title)}")


def error_exit(message: str) -> None:
    """
    Prints a GitHub Actions-formatted error message and exits the script.
    Args:
        message (str): The error message to log and print.
    """
    _get_log_function("ERROR", "❌ ERROR:")(message)
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


def main() -> None:
    """
    Main entry point for prepare_tf_branch_deploy.py.
    Validates input, loads configuration, processes arguments and paths, and writes outputs for GitHub Actions.
    """
    # --- Robust Input Validation ---
    if len(sys.argv) != 4:
        error_exit(
            f"Usage: {sys.argv[0]} <default_working_dir> <env_name> <dynamic_params_str>"
        )

    default_working_dir: str = sys.argv[1]
    env_name: str = sys.argv[2]
    dynamic_params_str: str = sys.argv[3]

    log_debug(f"Script received default_working_dir: '{default_working_dir}'")
    log_debug(f"Script received env_name: '{env_name}'")
    log_debug(f"Script received dynamic_params_str: '{dynamic_params_str}'")

    if not isinstance(default_working_dir, str) or not default_working_dir.strip():
        error_exit("Invalid or empty working directory argument provided to script.")
    if not isinstance(env_name, str) or not env_name.strip():
        error_exit("Invalid or empty environment name argument provided to script.")
    if not isinstance(dynamic_params_str, str):
        error_exit("Invalid dynamic_params_str argument provided to script.")

    # --- GITHUB_OUTPUT Validation ---
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        error_exit("GITHUB_OUTPUT environment variable not set. Cannot write outputs.")
    if not Path(output_path).parent.exists():
        error_exit(
            f"Parent directory for GITHUB_OUTPUT ('{Path(output_path).parent}') does not exist or is not accessible."
        )

    base_repo_path_for_tf_code = Path(os.getcwd())
    log_debug(
        f"Script executing from base_repo_path_for_tf_code (repo_checkout): {base_repo_path_for_tf_code}"
    )

    original_repo_root_path = Path(os.getenv("GITHUB_WORKSPACE"))
    log_debug(f"Original repository root (GITHUB_WORKSPACE): {original_repo_root_path}")

    # --- Load Configuration File ---
    config_file_name = ".tf-branch-deploy.yml"

    config_path = original_repo_root_path / config_file_name
    config: Dict[str, Any] = {}
    if config_path.is_file():
        log_info(
            f"✅ Found {config_file_name} at '{config_path}'. Parsing configuration for environment: '{env_name}'"
        )
        with open(config_path, "r") as f:
            try:
                config = yaml.safe_load(f) or {}
                log_debug(f"Loaded config: {config}")
            except yaml.YAMLError as e:
                error_exit(f"Error parsing {config_file_name}: {e}")
    else:
        log_info(
            f"⚠️ No {config_file_name} found at '{config_path}'. Using action defaults and assuming 'production' environment configuration."
        )

    # --- Validate Environment (if specified) ---
    if (
        env_name
        and env_name != "production"
        and env_name not in config.get("environments", {})
    ):
        error_exit(
            f"Configuration Error: Environment '{env_name}' not found in '{config_file_name}'."
        )

    # --- Determine Effective Terraform Working Directory ---
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
        f"Calculated effective Terraform working directory: '{effective_working_dir_for_output}' (relative to repo_checkout)"
    )

    # --- Build Terraform Arguments: init, plan, apply ---
    init_args_list: List[str] = []
    plan_args_list: List[str] = []
    apply_args_list: List[str] = []

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

    apply_args_list.extend(process_args(config, env_name, "apply-args", ""))
    log_debug(f"Collected all apply args: {apply_args_list}")

    # --- Layer on dynamic flags from comment with robust sanitization ---
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

    plan_args_list.extend(dynamic_flags)

    # --- Write final values to GitHub Actions Output ---
    final_init_args_str: str = " ".join(shlex.quote(arg) for arg in init_args_list)
    final_plan_args_str: str = " ".join(shlex.quote(arg) for arg in plan_args_list)
    final_apply_args_str: str = " ".join(shlex.quote(arg) for arg in apply_args_list)

    try:
        with open(output_path, "a") as f:
            f.write(f"working_dir={effective_working_dir_for_output}\n")
            f.write(f"init_args={final_init_args_str}\n")
            f.write(f"plan_args={final_plan_args_str}\n")
            f.write(f"apply_args={final_apply_args_str}\n")
        log_debug(f"Successfully wrote outputs to GITHUB_OUTPUT: {output_path}")
    except Exception as e:
        error_exit(f"Failed to write to GITHUB_OUTPUT file '{output_path}': {e}")

    log_section("📝 terraform-branch-deploy configuration summary:")
    log_info(
        f"📁 Terraform Working Directory (relative to repo_checkout): {effective_working_dir_for_output}"
    )
    log_info(f"🏗️  Terraform Init Arguments: {final_init_args_str}")
    log_info(f"📋 Terraform Plan Arguments: {final_plan_args_str}")
    log_info(f"🚀 Terraform Apply Arguments: {final_apply_args_str}")
    log_info("✅ Configuration prepared for Terraform execution.")


if __name__ == "__main__":
    main()
