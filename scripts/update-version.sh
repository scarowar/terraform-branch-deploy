#!/usr/bin/env bash
# Update public terraform-branch-deploy version references
# Usage: ./scripts/update-version.sh
#
# This script reads the version from docs/includes/version.txt
# and updates all @scarowar/terraform-branch-deploy references
# to use that version.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
VERSION_FILE="$ROOT_DIR/docs/includes/version.txt"

if [[ ! -f "$VERSION_FILE" ]]; then
    echo "Error: $VERSION_FILE not found" >&2
    exit 1
fi

VERSION=$(cat "$VERSION_FILE" | tr -d '\n')

if [[ -z "$VERSION" ]]; then
    echo "Error: Version file is empty" >&2
    exit 1
fi

echo "Updating all references to version: $VERSION"

while read -r file; do
    full_path="$ROOT_DIR/$file"
    if grep -q "terraform-branch-deploy@" "$full_path"; then
        # Use more permissive regex for versions/SHAs
        sed -Ei "s|terraform-branch-deploy@[a-zA-Z0-9][a-zA-Z0-9._-]*|terraform-branch-deploy@$VERSION|g" "$full_path"
        echo "  Updated: $file"
    fi
done < <(git -C "$ROOT_DIR" ls-files "*.md" "*.yml" "*.yaml")

echo "Done. All references now use @$VERSION"
