#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
    echo "Usage: make new-lib NAME=<library-name>"
    echo "Example: make new-lib NAME=ninja-persistence"
    exit 1
fi

NAME="$1"
PKG_NAME=$(echo "$NAME" | tr '-' '_')
LIB_DIR="libs/$NAME"

if [ -d "$LIB_DIR" ]; then
    echo "❌ Library $LIB_DIR already exists."
    exit 1
fi

echo "📦 Creating library: $NAME ($PKG_NAME)"

mkdir -p "$LIB_DIR/src/$PKG_NAME" "$LIB_DIR/tests"

cat > "$LIB_DIR/pyproject.toml" << PYEOF
[project]
name = "$NAME"
version = "0.1.0"
description = ""
requires-python = ">=3.12"
dependencies = ["pydantic>=2.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/$PKG_NAME"]
PYEOF

cat > "$LIB_DIR/src/$PKG_NAME/__init__.py" << INITEOF
"""$NAME library."""
INITEOF

cat > "$LIB_DIR/tests/test_${PKG_NAME}_imports.py" << TESTEOF
def test_${PKG_NAME}_imports():
    import $PKG_NAME

    assert $PKG_NAME is not None
TESTEOF

echo "✅ Created $LIB_DIR"
echo ""
echo "Next steps:"
echo "  1. Update description in $LIB_DIR/pyproject.toml"
echo "  2. Add to root pyproject.toml dependencies + [tool.uv.sources]"
echo "  3. Run: uv sync"
echo "  4. Run: make test"
