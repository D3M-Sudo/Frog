#!/bin/bash
#
# Release script for Anura
# Automatically pins tessdata commit SHA and creates git tag
#
# Usage: ./build-aux/release.sh <version> [tessdata_commit]
# Example: ./build-aux/release.sh 0.1.4 4767ea922bcc460e70b87b1d303ebdfed0e3060b

set -e

VERSION="$1"
TESSDATA_COMMIT="${2:-923915d4ced2a7235221788285785a29c4a42d4a}"

if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version> [tessdata_commit]"
    echo "Example: $0 0.1.4"
    echo "Example with custom tessdata commit: $0 0.1.4 abc123..."
    exit 1
fi

# Validate version format
if ! echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$'; then
    echo "Error: Version must be in format X.Y.Z or X.Y.Z.W (e.g., 0.1.4 or 0.1.4.3)"
    exit 1
fi

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MANIFEST_FILE="$PROJECT_ROOT/flatpak/io.github.d3msudo.anura.json"
METAINFO_FILE="$PROJECT_ROOT/data/io.github.d3msudo.anura.metainfo.xml.in"
MESON_BUILD_FILE="$PROJECT_ROOT/meson.build"
DATE=$(date +%Y-%m-%d)

echo "=== Anura Release $VERSION ==="
echo "Tessdata commit: $TESSDATA_COMMIT"
echo "Release date: $DATE"
echo ""

# Update meson.build with new version
echo "Updating $MESON_BUILD_FILE with version $VERSION..."
if [ -f "$MESON_BUILD_FILE" ]; then
    # Update version in meson.build (format: version: 'X.Y.Z')
    sed -i "s/version: '[0-9]\+\.[0-9]\+\.[0-9]\+'/version: '$VERSION'/" "$MESON_BUILD_FILE"
    if grep -q "version: '$VERSION'" "$MESON_BUILD_FILE"; then
        echo "✓ $MESON_BUILD_FILE updated successfully"
        git add "$MESON_BUILD_FILE"
    else
        echo "✗ Failed to update $MESON_BUILD_FILE"
        exit 1
    fi
else
    echo "⚠ $MESON_BUILD_FILE not found, skipping"
fi

echo ""

# Update manifest with pinned tessdata commit
echo "Updating $MANIFEST_FILE with pinned tessdata commit..."
sed -i "s|tessdata_fast/raw/[a-f0-9]*/|tessdata_fast/raw/${TESSDATA_COMMIT}/|g" "$MANIFEST_FILE"

# Verify the change was made
if grep -q "tessdata_fast/raw/${TESSDATA_COMMIT}/" "$MANIFEST_FILE"; then
    echo "✓ Manifest updated successfully"
else
    echo "✗ Failed to update manifest"
    exit 1
fi

# Update metainfo.xml with new release
echo ""
echo "Updating $METAINFO_FILE with new release entry..."

# Create new release entry
RELEASE_ENTRY="    <release version=\"$VERSION\" type=\"stable\" date=\"$DATE\">
      <description>
        <!-- TODO: Add release notes before publishing -->
        <p>Release $VERSION.</p>
      </description>
    </release>"

# Insert after the <releases> opening tag
if grep -q '<releases>' "$METAINFO_FILE"; then
    # Use sed to insert after <releases>
    sed -i "/<releases>/a\\$RELEASE_ENTRY" "$METAINFO_FILE"
    echo "✓ Metainfo updated successfully"
else
    echo "✗ Could not find <releases> tag in metainfo file"
    exit 1
fi

# Show summary
echo ""
echo "=== Summary of changes ==="
echo "Files modified:"
echo "  - $MESON_BUILD_FILE (version bumped to $VERSION)"
echo "  - $MANIFEST_FILE (tessdata pinned to $TESSDATA_COMMIT)"
echo "  - $METAINFO_FILE (release $VERSION added)"
echo ""

# Git operations
echo "=== Git operations ==="
echo "Adding files to git..."
git add "$MANIFEST_FILE" "$METAINFO_FILE"

echo "Creating commit..."
git commit -m "Release v$VERSION

- Bump version to $VERSION in meson.build
- Pin tessdata to commit $TESSDATA_COMMIT
- Update metainfo for v$VERSION release"

echo "Creating tag v$VERSION..."
git tag -a "v$VERSION" -m "Anura v$VERSION

Release highlights:
- Tessdata models pinned to commit $TESSDATA_COMMIT
- See CHANGELOG.md for full details"

echo ""
echo "=== Release v$VERSION prepared successfully ==="
echo ""
echo "Next steps:"
echo "  1. Review the commit: git show HEAD"
echo "  2. Push to remote: git push origin main --tags"
echo "  3. The CI will build the Flatpak automatically"
echo ""
echo "To push now, run:"
echo "  git push origin main --tags"
