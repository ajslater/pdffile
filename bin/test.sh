#!/bin/bash
# Run all tests
set -euxo pipefail
mkdir -p test-results
export PYTHONPATH=.
LOGLEVEL=DEBUG uvx pytest "$@"
# pytest-cov leaves .coverage.$HOST.$PID.$RAND files around while coverage itself doesn't
uvx coverage erase || true
