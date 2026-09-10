#!/bin/bash
# setup-gschema.sh
#
# Setup script for GSettings schema compilation for Anura testing
# This script compiles the GSettings schema needed for GTK-dependent tests

set -e

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔧 Setting up GSettings schema for Anura testing..."

# Create build directory
mkdir -p "$PROJECT_ROOT/builddir"

# Copy schema file
echo "📄 Copying schema file..."
cp "$PROJECT_ROOT/data/io.github.d3msudo.anura.gschema.xml" "$PROJECT_ROOT/builddir/"

# Compile schema
echo "🔨 Compiling GSettings schema..."
glib-compile-schemas "$PROJECT_ROOT/builddir/"

# Verify compilation
if [ -f "$PROJECT_ROOT/builddir/gschemas.compiled" ]; then
    echo "✅ GSettings schema compiled successfully!"
    echo ""
    echo "🚀 To run GTK tests, use:"
    echo "export GSETTINGS_SCHEMA_DIR=\"$PROJECT_ROOT/builddir\""
    echo "uv run env PYTHONPATH=\"/usr/lib/python3/dist-packages:\$PYTHONPATH\" GI_TYPELIB_PATH=\"/usr/lib/x86_64-linux-gnu/girepository-1.0:/usr/lib/girepository-1.0\" GSETTINGS_SCHEMA_DIR=\"$PROJECT_ROOT/builddir\" pytest tests/test_tts_service.py -v"
    echo ""
    echo "Or run the complete GTK test suite:"
    echo "export GSETTINGS_SCHEMA_DIR=\"$PROJECT_ROOT/builddir\""
    echo "uv run env PYTHONPATH=\"/usr/lib/python3/dist-packages:\$PYTHONPATH\" GI_TYPELIB_PATH=\"/usr/lib/x86_64-linux-gnu/girepository-1.0:/usr/lib/girepository-1.0\" GSETTINGS_SCHEMA_DIR=\"$PROJECT_ROOT/builddir\" pytest tests/test_clipboard_service.py tests/test_screenshot_service.py tests/test_share_service.py tests/test_tts_service.py tests/test_notification_service.py -v"
else
    echo "❌ Failed to compile GSettings schema"
    exit 1
fi
