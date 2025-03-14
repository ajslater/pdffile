#!/bin/bash
# Get version or set version in pyproject.toml.
set -euo pipefail
VERSION="${1:-}"
TOML_PATH=--toml-path=pyproject.toml
if [ "$VERSION" = "" ]; then
  uv run toml get "$TOML_PATH" project.version
else
  uv run toml set "$TOML_PATH" project.version "$VERSION"
fi
