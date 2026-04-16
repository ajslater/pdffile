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

# hadolint ignore=DL4006
RUN curl -fsSL https://bun.com/install | bash

WORKDIR /app

COPY cfg ./cfg
COPY pdffile ./pdffile
COPY bun.lock package.json pyproject.toml uv.lock Makefile README.md ./
RUN make install

COPY . .
