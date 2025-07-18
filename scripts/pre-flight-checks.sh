#!/bin/bash
set -euo pipefail

echo "--- Starting Pre-flight Checks ---"

echo "::group::Validate Configuration File"
echo "USER_REPO_PATH=${USER_REPO_PATH:-unset}"
CONFIG_FILE="${USER_REPO_PATH}/.tf-branch-deploy.yml"
echo "CONFIG_FILE=${CONFIG_FILE}"
ls -l "${CONFIG_FILE}" || echo "Config file not found!"
cat "${CONFIG_FILE}" || echo "Cannot read config file!"
yq --version || echo "yq not found!"
if [[ -z "${USER_REPO_PATH:-}" ]]; then
  echo "::error::USER_REPO_PATH environment variable is required but not set"
  exit 1
fi

# Check if configuration file exists and validate its contents
if [[ -f "${CONFIG_FILE}" ]]; then
  echo "🔍 Analyzing configuration file..."
  # Extract all environment names from the configuration
  if ! ENVS=$(yq e '.environments | keys | .[]' "${CONFIG_FILE}" 2>/dev/null | tr '\n' ',' | sed 's/,$//'); then
    echo "❌ Failed to parse environments from .tf-branch-deploy.yml. Please check YAML syntax." >&2
    exit 1
  fi
  if [[ -z "${ENVS}" ]]; then
    echo "❌ No environments defined in .tf-branch-deploy.yml. At least one environment must be present under 'environments'." >&2
    exit 1
  fi

  # Validate default environment configuration
  if ! DEFAULT_ENV=$(yq e '."default-environment"' "${CONFIG_FILE}" 2>/dev/null); then
    echo "❌ Failed to parse default-environment from .tf-branch-deploy.yml. Please check YAML syntax." >&2
    exit 1
  fi
  if [[ -z "${DEFAULT_ENV}" ]] || [[ "${DEFAULT_ENV}" = "null" ]]; then
    echo "❌ 'default-environment' is missing or empty at the root of .tf-branch-deploy.yml." >&2
    exit 1
  fi
  if ! echo "${ENVS}" | grep -qw "${DEFAULT_ENV}"; then
    echo "❌ 'default-environment' ('${DEFAULT_ENV}') is not defined in 'environments'." >&2
    exit 1
  fi

  # Validate production environments configuration
  if ! PROD_ENVS=$(yq e '."production-environments" | join(",")' "${CONFIG_FILE}" 2>/dev/null); then
    echo "❌ Failed to parse production-environments from .tf-branch-deploy.yml. Please check YAML syntax." >&2
    exit 1
  fi
  if [[ -z "${PROD_ENVS}" ]] || [[ "${PROD_ENVS}" = "null" ]]; then
    echo "❌ 'production-environments' is missing or empty at the root of .tf-branch-deploy.yml." >&2
    exit 1
  fi
  IFS=',' read -ra PROD_ENV_ARR <<< "${PROD_ENVS}"
  for prod_env in "${PROD_ENV_ARR[@]}"; do
    if ! echo "${ENVS}" | grep -qw "${prod_env}"; then
      echo "❌ production-environment '${prod_env}' is not defined in 'environments'." >&2
      exit 1
    fi
  done

  # Output discovered configuration
  echo "✅ Configuration file validation successful"
  echo "📋 Discovered environments: ${ENVS}"
  echo "🎯 Default environment: ${DEFAULT_ENV}"
  echo "🏭 Production environments: ${PROD_ENVS}"
  {
    echo "available_envs=${ENVS}"
    echo "default_environment=${DEFAULT_ENV}"
    echo "production_environments=${PROD_ENVS}"
  } >> "${GITHUB_OUTPUT}"
else
  # Handle missing configuration file with defaults
  echo "❌ No configuration file found, using defaults"
  {
    echo "available_envs=production"
    echo "default_environment=production"
    echo "production_environments=production"
  } >> "${GITHUB_OUTPUT}"
  echo "::notice::No .tf-branch-deploy.yml found at '${CONFIG_FILE}'. Proceeding with default 'production' environment only."
fi
echo "::endgroup::"

echo "🎉 Pre-flight Checks Complete"
