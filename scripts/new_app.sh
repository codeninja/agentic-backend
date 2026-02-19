#!/usr/bin/env bash
set -e

if [ -z "$1" ]; then
    echo "Usage: make new-app NAME=<app-name>"
    echo "Example: make new-app NAME=ninja-worker"
    exit 1
fi

NAME="$1"
PKG_NAME=$(echo "$NAME" | tr '-' '_')
APP_DIR="apps/$NAME"

if [ -d "$APP_DIR" ]; then
    echo "❌ App $APP_DIR already exists."
    exit 1
fi

echo "🚀 Creating app: $NAME ($PKG_NAME)"

mkdir -p "$APP_DIR/src/$PKG_NAME" "$APP_DIR/tests"

cat > "$APP_DIR/pyproject.toml" << PYEOF
[project]
name = "$NAME"
version = "0.1.0"
description = ""
requires-python = ">=3.12"
dependencies = ["ninja-core"]

[tool.uv.sources]
ninja-core = { workspace = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/$PKG_NAME"]
PYEOF

cat > "$APP_DIR/src/$PKG_NAME/__init__.py" << INITEOF
"""$NAME — thin composition shell. No business logic here."""
INITEOF

cat > "$APP_DIR/tests/test_${PKG_NAME}_imports.py" << TESTEOF
def test_${PKG_NAME}_imports():
    import $PKG_NAME

    assert $PKG_NAME is not None
TESTEOF

echo "✅ Created $APP_DIR"
echo ""
echo "Next steps:"
echo "  1. Update description in $APP_DIR/pyproject.toml"
echo "  2. Add workspace lib dependencies to [project.dependencies] + [tool.uv.sources]"
echo "  3. Add to root pyproject.toml dependencies + [tool.uv.sources]"
echo "  4. Run: uv sync"
echo "  5. Run: make test"
echo ""
echo "⚠️  Remember: Apps are composition only. All logic goes in libs/."
