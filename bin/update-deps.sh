#!/bin/bash
# Update python and npm dependencies
set -euo pipefail
uv sync --no-install-project
uv tree --outdated
npm update
npm outdated
