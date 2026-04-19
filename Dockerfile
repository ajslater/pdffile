FROM oven/bun:latest AS bun-source
FROM nikolaik/python-nodejs:python3.14-nodejs24
LABEL maintainer="AJ Slater <aj@slater.net>"

# hadolint ignore=DL3008
RUN apt-get clean \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        bash \
        mupdf \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=bun-source /usr/local/bin/bun /usr/local/bin/bun
COPY --from=bun-source /usr/local/bin/bunx /usr/local/bin/bunx

WORKDIR /app

COPY cfg ./cfg
COPY pdffile ./pdffile
COPY bun.lock package.json pyproject.toml uv.lock Makefile README.md ./
RUN make install

COPY . .
