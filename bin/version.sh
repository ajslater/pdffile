#!/bin/bash
# Get version or set version in pyproject.toml.
set -euo pipefail
VERSION="${1:-}"
if [ "$VERSION" = "" ]; then
  uvx toml get --toml-path=pyproject.toml project.version
else
  uvx toml set --toml-path=pyproject.toml project.version "$VERSION"
fi
