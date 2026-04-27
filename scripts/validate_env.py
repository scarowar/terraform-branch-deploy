#!/usr/bin/env python3
"""Validate TF_BD_ENVIRONMENT against the branch-deploy config file.

Usage: python3 validate_env.py <config-path> <environment-name>

Exits 0 if the environment exists in the config, 1 otherwise.
Uses PyYAML for reliable YAML parsing (available on GitHub Actions runners).
"""

import sys

try:
    import yaml
except ImportError:
    print("::error::PyYAML is not installed. Cannot validate environment.")
    sys.exit(1)


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <config-path> <environment>")
        return 1

    config_path = sys.argv[1]
    target_env = sys.argv[2]

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        print(f"::error::Failed to read config '{config_path}': {exc}")
        return 1

    if not isinstance(config, dict):
        print(f"::error::Config '{config_path}' is not a valid YAML mapping")
        return 1

    envs = config.get("environments", {})
    if not isinstance(envs, dict):
        print(f"::error::'environments' key in '{config_path}' is not a mapping")
        return 1

    if target_env not in envs:
        valid = ", ".join(envs.keys())
        print(f"::error::TF_BD_ENVIRONMENT [{target_env}] not found in {config_path}")
        print(f"::error::Valid environments: [{valid}]")
        print("::error::This may indicate env var tampering between trigger and execute modes.")
        return 1

    print(f"Environment [{target_env}] verified against config")
    return 0


if __name__ == "__main__":
    sys.exit(main())
