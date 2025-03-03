#!/bin/bash
# Lint checks
set -euxo pipefail

####################
###### Python ######
####################
uvx ruff check .
uvx ruff format --check .
pyright
uvx vulture .
if [ "$(uname)" = "Darwin" ]; then
  # Radon is only of interest to development
  uvx radon mi --min B .
  uvx radon cc --min C .
fi
# uvx djlint templates --profile=django --lint

############################################
##### Javascript, JSON, Markdown, YAML #####
############################################
npm run lint

################################
###### Docker, Shell, Etc ######
################################
if [ "$(uname)" = "Darwin" ]; then
  # Hadolint & shfmt are difficult to install on linux
  # shellcheck disable=2035
  # hadolint *Dockerfile
  shellharden ./**/*.sh
  # subdirs aren't copied into docker builder
  # .env files aren't copied into docker
  shellcheck --external-sources ./**/*.sh
  # circleci config validate .circleci/config.yml
fi
./bin/roman.sh -i .prettierignore .
uvx codespell .
