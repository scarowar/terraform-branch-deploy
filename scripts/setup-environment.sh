#!/bin/bash
set -euo pipefail

echo "--- Starting Environment Setup ---"

# Determine if sudo is available and needed
SUDO=""
if command -v sudo >/dev/null 2>&1 && [[ "${EUID}" -ne 0 ]]; then
  SUDO="sudo"
fi

# Verify Required System Utilities
echo "::group::Verify Required System Utilities"
REQUIRED_TOOLS=("git" "curl" "unzip")
MISSING_TOOLS=()

echo "Checking for required system utilities..."
for tool in "${REQUIRED_TOOLS[@]}"; do
  if command -v "${tool}" >/dev/null 2>&1; then
    echo "✅ ${tool} is available"
  else
    echo "❌ ${tool} is missing"
    MISSING_TOOLS+=("${tool}")
  fi
done

# Only install missing tools if any are missing
if [[ ${#MISSING_TOOLS[@]} -eq 0 ]]; then
  echo "✅ All required system utilities are already available"
else
  echo "⬇️ Installing missing utilities: ${MISSING_TOOLS[*]}"

  if [[ ${RUNNER_OS} == "Linux" ]]; then
    if command -v apt-get >/dev/null 2>&1; then
      echo "Using apt-get to install missing dependencies..."
      ${SUDO} apt-get update -y
      for tool in "${MISSING_TOOLS[@]}"; do
        echo "Installing ${tool}..."
        ${SUDO} apt-get install -y "${tool}"
      done
    elif command -v yum >/dev/null 2>&1; then
      echo "Using yum to install missing dependencies..."
      ${SUDO} yum makecache
      for tool in "${MISSING_TOOLS[@]}"; do
        echo "Installing ${tool}..."
        ${SUDO} yum install -y "${tool}"
      done
    else
      echo "::error::Neither apt-get nor yum found on Linux. Cannot install missing tools: ${MISSING_TOOLS[*]}"
      exit 1
    fi
  elif [[ ${RUNNER_OS} == "macOS" ]]; then
    if command -v brew >/dev/null 2>&1; then
      echo "Using Homebrew to install missing dependencies..."
      for tool in "${MISSING_TOOLS[@]}"; do
        echo "Installing ${tool}..."
        brew install "${tool}"
      done
    else
      echo "::error::Homebrew not found on macOS. Cannot install missing tools: ${MISSING_TOOLS[*]}"
      exit 1
    fi
  elif [[ ${RUNNER_OS} == "Windows" ]]; then
    echo "::error::Windows detected with missing tools: ${MISSING_TOOLS[*]}. Please ensure these are pre-installed."
    exit 1
  else
    echo "::error::Unsupported OS: ${RUNNER_OS}. Cannot install missing tools: ${MISSING_TOOLS[*]}"
    exit 1
  fi

  # Verify installation
  echo "Verifying installation of missing tools..."
  for tool in "${MISSING_TOOLS[@]}"; do
    if command -v "${tool}" >/dev/null 2>&1; then
      echo "✅ ${tool} successfully installed"
    else
      echo "::error::Failed to install ${tool}"
      exit 1
    fi
  done
fi
echo "::endgroup::"

echo "::group::Install CLI tools (yq and tfcmt)"

# Set default versions (can be overridden by environment variables)
YQ_VERSION="${YQ_VERSION:-v4.45.4}"
TFCMT_VERSION="${TFCMT_VERSION:-v4.14.7}"

# Install yq (YAML Processor)
if command -v yq >/dev/null 2>&1; then
  echo "✅ yq is already installed. Version:"
  yq --version
else
  echo "⬇️ Installing yq ${YQ_VERSION}..."
  OS_TYPE=$(uname -s)
  ARCH=$(uname -m)

  case "${OS_TYPE}" in
    Linux)
      case "${ARCH}" in
        x86_64) ARCH_TAG=amd64 ;;
        aarch64) ARCH_TAG=arm64 ;;
        *) echo "::error::Unsupported Linux architecture for yq: ${ARCH}" && exit 1 ;;
      esac
      YQ_URL="https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_linux_${ARCH_TAG}"
      DEST_PATH="/usr/local/bin/yq"
      ;;
    Darwin)
      case "${ARCH}" in
        x86_64) ARCH_TAG=amd64 ;;
        arm64) ARCH_TAG=arm64 ;;
        *) echo "::error::Unsupported macOS architecture for yq: ${ARCH}" && exit 1 ;;
      esac
      YQ_URL="https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_darwin_${ARCH_TAG}"
      DEST_PATH="/usr/local/bin/yq"
      ;;
    MINGW*|CYGWIN*|MSYS*)
      ARCH_TAG=amd64
      YQ_URL="https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_windows_${ARCH_TAG}.exe"
      DEST_PATH="/usr/local/bin/yq.exe"
      ;;
    *)
      echo "::error::Unsupported OS for yq installation: ${OS_TYPE}"
      exit 1
      ;;
  esac

  echo "Attempting to download yq from: ${YQ_URL} to ${DEST_PATH}"
  TEMP_YQ_PATH=$(mktemp)
  trap 'rm -f -- "$TEMP_YQ_PATH"' EXIT

  if ! curl -sSL "${YQ_URL}" -o "${TEMP_YQ_PATH}"; then
    echo "::error::Failed to download yq from ${YQ_URL}. Check network connectivity or URL."
    exit 1
  fi

  # Checksum verification for yq
  CHECKSUM_URL="https://github.com/mikefarah/yq/releases/download/${YQ_VERSION}/yq_checksums.txt"
  echo "Downloading checksums from ${CHECKSUM_URL}"
  if ! CHECKSUM_CONTENT=$(curl -sSL "${CHECKSUM_URL}"); then
      echo "::error::Failed to download checksums for yq from ${CHECKSUM_URL}"
      exit 1
  fi
  YQ_FILENAME=$(basename "${YQ_URL}")
  EXPECTED_CHECKSUM=$(echo "${CHECKSUM_CONTENT}" | grep "${YQ_FILENAME}" | awk '{print $1}')

  if [[ -z "${EXPECTED_CHECKSUM}" ]]; then
      echo "::error::Could not find checksum for ${YQ_FILENAME} in checksum file."
      exit 1
  fi

  echo "Verifying checksum for yq..."
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_CHECKSUM=$(sha256sum "${TEMP_YQ_PATH}" | awk '{print $1}')
  else
    ACTUAL_CHECKSUM=$(shasum -a 256 "${TEMP_YQ_PATH}" | awk '{print $1}')
  fi

  if [[ "${ACTUAL_CHECKSUM}" != "${EXPECTED_CHECKSUM}" ]]; then
    echo "::error::Checksum verification failed for yq. Expected ${EXPECTED_CHECKSUM}, got ${ACTUAL_CHECKSUM}"
    exit 1
  fi
  echo "✅ Checksum verified for yq"

  ${SUDO} mv "${TEMP_YQ_PATH}" "${DEST_PATH}"
  ${SUDO} chmod +x "${DEST_PATH}"
  echo "✅ yq installed successfully."
  trap - EXIT
fi

# Install tfcmt
if command -v tfcmt >/dev/null 2>&1; then
  echo "✅ tfcmt is already installed. Version:"
  tfcmt --version
else
  echo "⬇️ Installing tfcmt ${TFCMT_VERSION}..."
  OS_TYPE=$(uname -s | tr '[:upper:]' '[:lower:]')
  ARCH=$(uname -m)

  case "${ARCH}" in
    x86_64) ARCH_TAG=amd64 ;;
    arm64) ARCH_TAG=arm64 ;;
    aarch64) ARCH_TAG=arm64 ;;
    *) echo "::error::Unsupported architecture for tfcmt: ${ARCH}" && exit 1 ;;
  esac

  if [[ "${OS_TYPE}" == "darwin" ]]; then
    ARCH_TAG_MAC="universal"
  fi

  TFCMT_FILENAME="tfcmt_${OS_TYPE}_${ARCH_TAG_MAC:-${ARCH_TAG}}.tar.gz"
  TFCMT_URL="https://github.com/suzuki-shunsuke/tfcmt/releases/download/${TFCMT_VERSION}/${TFCMT_FILENAME}"

  if [[ "${RUNNER_OS}" == "Windows" ]]; then
    TFCMT_FILENAME="tfcmt_${TFCMT_VERSION}_windows_amd64.zip"
    TFCMT_URL="https://github.com/suzuki-shunsuke/tfcmt/releases/download/${TFCMT_VERSION}/${TFCMT_FILENAME}"
  fi

  TEMP_DIR=$(mktemp -d)
  trap 'rm -rf -- "$TEMP_DIR"' EXIT

  echo "Attempting to download tfcmt from: ${TFCMT_URL}"
  if ! curl -sSL "${TFCMT_URL}" -o "${TEMP_DIR}/${TFCMT_FILENAME}"; then
    echo "::error::Failed to download tfcmt archive from ${TFCMT_URL}."
    exit 1
  fi

  # Checksum verification
  CHECKSUM_URL="https://github.com/suzuki-shunsuke/tfcmt/releases/download/${TFCMT_VERSION}/tfcmt_${TFCMT_VERSION}_checksums.txt"
  echo "Downloading checksums from ${CHECKSUM_URL}"
  if ! CHECKSUM_CONTENT=$(curl -sSL "${CHECKSUM_URL}"); then
      echo "::error::Failed to download checksums for tfcmt from ${CHECKSUM_URL}"
      exit 1
  fi
  EXPECTED_CHECKSUM=$(echo "${CHECKSUM_CONTENT}" | grep "${TFCMT_FILENAME}" | awk '{print $1}')

  if [[ -z "${EXPECTED_CHECKSUM}" ]]; then
      echo "::error::Could not find checksum for ${TFCMT_FILENAME} in checksum file."
      exit 1
  fi

  echo "Verifying checksum for ${TFCMT_FILENAME}..."
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_CHECKSUM=$(sha256sum "${TEMP_DIR}/${TFCMT_FILENAME}" | awk '{print $1}')
  else
    ACTUAL_CHECKSUM=$(shasum -a 256 "${TEMP_DIR}/${TFCMT_FILENAME}" | awk '{print $1}')
  fi

  if [[ "${ACTUAL_CHECKSUM}" != "${EXPECTED_CHECKSUM}" ]]; then
    echo "::error::Checksum verification failed for tfcmt. Expected ${EXPECTED_CHECKSUM}, got ${ACTUAL_CHECKSUM}"
    exit 1
  fi
  echo "✅ Checksum verified for tfcmt"

  if [[ "${RUNNER_OS}" == "Windows" ]]; then
    unzip -q "${TEMP_DIR}/${TFCMT_FILENAME}" -d "${TEMP_DIR}"
    ${SUDO} cp "${TEMP_DIR}/tfcmt.exe" "/usr/local/bin/tfcmt.exe"
    echo "✅ tfcmt installed successfully on Windows."
  else
    if ! ${SUDO} tar -xz -f "${TEMP_DIR}/${TFCMT_FILENAME}" -C /usr/local/bin; then
      echo "::error::Failed to extract tfcmt from ${TEMP_DIR}/${TFCMT_FILENAME}."
      exit 1
    fi
    echo "✅ tfcmt installed successfully."
  fi
  trap - EXIT
fi

# Verify all CLI tools are properly installed and accessible
echo "Verifying installed CLI tools:"
CLI_TOOLS=("yq" "tfcmt")
VERIFICATION_FAILED=false

for tool in "${CLI_TOOLS[@]}"; do
  if command -v "${tool}" >/dev/null 2>&1; then
    # Get version info with error handling
    VERSION_OUTPUT=$(${tool} --version 2>&1 | head -n 1) || VERSION_OUTPUT="(version unavailable)"
    echo "✅ ${tool} found: ${VERSION_OUTPUT}"
  else
    echo "❌ ${tool} not found after installation!"
    VERIFICATION_FAILED=true
  fi
done

if [[ "${VERIFICATION_FAILED}" = true ]]; then
  echo "::error::One or more CLI tools failed verification. Please check the installation process."
  exit 1
fi

echo "✅ All CLI tools are installed and available in PATH."
echo "::endgroup::"

echo "::group::Setup Python Virtual Environment"
if [[ -z "${USER_REPO_PATH:-}" ]]; then
  echo "::error::USER_REPO_PATH environment variable is required but not set"
  exit 1
fi
# Create virtual environment path outside user repo to avoid git clean operations
VENV_PATH="${GITHUB_WORKSPACE}/.venv-terraform-branch-deploy"

# Verify Python3 is available
if ! command -v python3 >/dev/null 2>&1; then
  echo "::error::python3 is not available. Please ensure Python 3 is installed."
  exit 1
fi

echo "Setting up Python virtual environment at: ${VENV_PATH}"
if ! python3 -m venv "${VENV_PATH}"; then
  echo "::error::Failed to create Python virtual environment"
  exit 1
fi

# Activate virtual environment
# shellcheck disable=SC1091
if ! source "${VENV_PATH}/bin/activate"; then
  echo "::error::Failed to activate Python virtual environment"
  exit 1
fi
echo "Python virtual environment activated."

echo "Upgrading pip..."
if ! pip install --upgrade pip; then
  echo "::error::Failed to upgrade pip"
  exit 1
fi
echo "pip upgraded."

echo "Installing Python dependencies from requirements.txt..."
if ! pip install -r "${SELF_ACTION_PATH}/scripts/requirements.txt"; then
  echo "::error::Failed to install Python dependencies"
  exit 1
fi
echo "✅ Python dependencies installed."
echo "::endgroup::"

echo "--- Environment Setup Complete ---"
