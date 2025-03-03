#!/bin/bash
# Update python and npm dependencies
set -euo pipefail
uv sync --no-install-project --all-extras
uv tree --all-groups --outdated | grep latest
npm update
npm outdated
