FROM nikolaik/python-nodejs:python3.13-nodejs23
LABEL maintainer="AJ Slater <aj@slater.net>"

# hadolint ignore=DL3008
RUN apt-get clean \
  && apt-get update \
  && apt-get install --no-install-recommends -y \
    bash \
    mupdf \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY bin ./bin
COPY .gitignore .prettierignore .remarkignore eslint.config.js package.json package-lock.json pyproject.toml uv.lock Makefile ./
RUN make install-all

COPY . .
