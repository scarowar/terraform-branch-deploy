#!/bin/bash
set -euo pipefail

echo "--- Starting Git Tag Management ---"

COMMAND="${1}"
shift

# Validate required environment variables
echo "::group::🔍 Validating Environment Variables"
REQUIRED_VARS=(
	"ENVIRONMENT"
	"RUN_ID"
	"SHA"
	"GITHUB_ACTOR"
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
	exit 1
fi

TAG_NAME="terraform-branch-deploy/plan/${ENVIRONMENT}/${RUN_ID}/${SHA}"
echo "✅ Environment validation complete"
echo "🏷️ Tag name: ${TAG_NAME}"
echo "::endgroup::"

create_tag() {
	echo "::group::🏷️ Creating Git Tag for Plan Artifact"
	TAG_MESSAGE="terraform-branch-deploy plan artifact from run ${RUN_ID}. Triggered by @${GITHUB_ACTOR} on $(date -u)."

	echo "🔧 Configuring git user for tag creation..."
	git config user.name "github-actions[bot]"
	git config user.email "github-actions[bot]@users.noreply.github.com"

	if git rev-parse -q --verify "refs/tags/${TAG_NAME}" >/dev/null; then
		echo "⚠️ Overwriting existing plan tag for this commit and environment: ${TAG_NAME}"
		git tag -f "${TAG_NAME}" "${SHA}" -m "${TAG_MESSAGE}"
	else
		echo "🆕 Creating new git tag: ${TAG_NAME}"
		git tag "${TAG_NAME}" "${SHA}" -m "${TAG_MESSAGE}"
	fi

	echo "📤 Pushing tag to remote repository..."
	if ! git push origin "refs/tags/${TAG_NAME}"; then
		echo "::warning::⚠️ Failed to push git tag normally. Attempting force push..."
		if ! git push -f origin "refs/tags/${TAG_NAME}"; then
			echo "::error::🚨 Failed to push git tag, even with force."
			echo "::error::💡 Ensure the workflow has 'contents: write' permission."
			exit 1
		fi
		echo "✅ Tag pushed successfully with force"
	else
		echo "✅ Tag pushed successfully"
	fi
	echo "🎉 Git tag creation complete"
	echo "::endgroup::"
}

delete_tag() {
	echo "::group::🧹 Cleaning Up Plan Tag After Apply"
	echo "🔍 Attempting to delete local tag: ${TAG_NAME}"
	if git tag -d "${TAG_NAME}"; then
		echo "✅ Local tag deleted: ${TAG_NAME}"
	else
		echo "::warning::⚠️ Local tag ${TAG_NAME} did not exist or could not be deleted."
	fi

	echo "🌐 Attempting to delete remote tag: ${TAG_NAME}"
	if git push --delete origin "${TAG_NAME}"; then
		echo "✅ Remote tag deleted: ${TAG_NAME}"
	else
		echo "::warning::⚠️ Remote tag ${TAG_NAME} did not exist or could not be deleted."
	fi

	echo "🎉 Plan tag cleanup complete"
	echo "::endgroup::"
}

case "${COMMAND}" in
create)
	create_tag
	;;
delete)
	delete_tag
	;;
*)
	echo "::error::❌ Unknown command '${COMMAND}' for manage-git-tags.sh" >&2
	echo "::error::💡 Supported commands: create, delete" >&2
	exit 1
	;;
esac

echo "--- Git Tag Management Complete ---"
