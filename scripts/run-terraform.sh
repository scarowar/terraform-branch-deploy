#!/bin/bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "::error::❌ No command supplied. Supported commands: plan, apply, rollback" >&2
  exit 1
fi
COMMAND=$1
shift

echo "--- Starting Terraform ${COMMAND^} Operation ---"

# Validate required environment variables
echo "::group::🔍 Validating Environment Variables"
REQUIRED_VARS=(
	"GITHUB_EVENT_ISSUE_NUMBER"
	"GITHUB_REPOSITORY_OWNER"
	"GITHUB_REPOSITORY_NAME"
	"SHA"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
	if [[ -z "${!var:-}" ]]; then
		echo "❌ Required environment variable ${var} is not set"
		MISSING_VARS+=("${var}")
	else
		echo "✅ ${var} is set"
	fi
done

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
	echo "::error::Missing required environment variables: ${MISSING_VARS[*]}"
	echo "::error::💡 Ensure all required environment variables are passed to the script."
	echo "::endgroup::"
	exit 1
fi

TFCMT_ISSUE_NUMBER=${GITHUB_EVENT_ISSUE_NUMBER}
PLAN_BINARY_FILE="tfplan-${SHA}.binary"
echo "✅ Environment validation complete"
echo "::endgroup::"

run_tfcmt() {
	local tf_command="${1}"
	shift
	local tf_args=("$@")

	echo "🔧 Preparing tfcmt command for terraform ${tf_command}..."

	local terraform_command_and_args=(
    terraform
    "${tf_command}"
    "${tf_args[@]}"
  )

	local tfcmt_command=(
    tfcmt "${tf_command}"
    --owner="${GITHUB_REPOSITORY_OWNER}"
    --repo="${GITHUB_REPOSITORY_NAME}"
    --sha="${SHA}"
    --pr="${TFCMT_ISSUE_NUMBER}"
    --
    "${terraform_command_and_args[@]}"
  )

	echo "🚀 Executing: ${tfcmt_command[*]}"
	"${tfcmt_command[@]}"
	local tfcmt_exit_code=$?

	echo "tfcmt_exit_code=${tfcmt_exit_code}" >>"${GITHUB_OUTPUT}"

	# Enhanced exit code handling with detailed feedback
	if [[ "${tfcmt_exit_code}" -eq 1 ]]; then
		echo "::error::🚨 Terraform ${tf_command} (via tfcmt) failed with a critical error."
		echo "::error::💡 Check the terraform configuration and resolve any syntax or runtime errors."
	elif [[ "${tf_command}" == "plan" ]] && [[ "${tfcmt_exit_code}" -eq 2 ]]; then
		echo "::notice::📝 Terraform plan (via tfcmt) indicates infrastructure changes are pending."
		echo "::notice::💡 Review the plan output in the pull request before proceeding with apply."
	elif [[ "${tfcmt_exit_code}" -eq 0 ]]; then
		echo "::notice::✅ Terraform ${tf_command} (via tfcmt) completed successfully."
	else
		echo "::warning::⚠️ Terraform ${tf_command} (via tfcmt) completed with non-zero exit code: ${tfcmt_exit_code}."
		echo "::warning::💡 Check the terraform output for warnings or unexpected behavior."
	fi

	return "${tfcmt_exit_code}"
}

run_tfcmt_with_exit() {
	run_tfcmt "$@"
	local exit_code=$?
	exit "${exit_code}"
}

case "${COMMAND}" in
plan)
	echo "::group::📋 Terraform Plan Generation"
	echo "🔍 Generating Terraform plan for infrastructure preview..."
	echo "📁 Plan will be saved as: ${PLAN_BINARY_FILE}"
	echo "🔗 Plan output will be posted to the pull request via tfcmt"
	echo "💡 Review the generated plan carefully before proceeding with apply"
	echo "::endgroup::"

	run_tfcmt_with_exit plan "$@" -out="${PLAN_BINARY_FILE}"
	;;
apply)
	echo "::group::🚀 Terraform Apply Execution"
	echo "⚡ Applying previously generated Terraform plan..."
	echo "📁 Using plan binary: ${PLAN_BINARY_FILE}"

	if [[ ! -f "${PLAN_BINARY_FILE}" ]]; then
		echo "::error::🚨 Terraform plan binary '${PLAN_BINARY_FILE}' not found."
		echo "::error::💡 Ensure a plan was generated for this commit and environment before applying."
		echo "::error::💡 Check that the plan artifact was properly downloaded from the previous run."
		exit 1
	fi

	echo "✅ Plan binary found and verified"
	echo "🔄 Applying infrastructure changes with auto-approval..."
	echo "::endgroup::"

	run_tfcmt_with_exit apply -auto-approve "$@" "${PLAN_BINARY_FILE}"
	;;
rollback)
	echo "::group::🚨 Emergency Rollback to Stable Branch"
	echo "🔄 Performing immediate plan and apply for stable branch rollback with tfcmt"
	echo "⚠️  This operation will revert infrastructure to the last known stable state"
	echo "💡 Rollback operations bypass normal plan/apply workflow for emergency recovery"
	echo "::endgroup::"

	PLAN_BINARY_FILE="rollback.plan"

	echo "::group::📋 Generating Rollback Plan"
	echo "🔍 Planning rollback deployment to validate stable branch state..."
	echo "📁 Rollback plan will be saved as: ${PLAN_BINARY_FILE}"
	run_tfcmt plan "$@" -out="${PLAN_BINARY_FILE}"
	plan_exit_code=$?
	echo "::endgroup::"

	if [[ "${plan_exit_code}" -eq 1 ]]; then
		echo "::error::🚨 Terraform plan for rollback failed with a critical error. Cannot proceed with apply."
		echo "::error::💡 Check the stable branch state and ensure Terraform configuration is valid."
		echo "::error::💡 Verify that the stable branch contains working terraform code."
		exit 1
	elif [[ "${plan_exit_code}" -eq 2 ]]; then
		echo "::notice::📝 Rollback plan shows infrastructure changes - this is expected for emergency rollbacks."
		echo "::notice::💡 Proceeding with rollback apply to restore stable state."
	fi

	echo "::group::🚀 Executing Rollback Apply"
	echo "⚡ Applying rollback plan to restore stable infrastructure state..."
	echo "🔄 Auto-approving rollback changes for emergency recovery..."
	echo "::endgroup::"
	run_tfcmt_with_exit apply -auto-approve "${PLAN_BINARY_FILE}"
	;;
*)
	echo "::error::❌ Unknown command '${COMMAND}' for run-terraform.sh" >&2
	echo "::error::💡 Supported commands: plan, apply, rollback" >&2
	exit 1
	;;
esac

# This line is intentionally unreachable as all execution paths exit explicitly
# shellcheck disable=SC2317
echo "--- Terraform ${COMMAND^} Operation Complete ---"
