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

WORKDIR /app

COPY cfg ./cfg
COPY pdffile ./pdffile
COPY package.json package-lock.json pyproject.toml uv.lock Makefile README.md ./
RUN make install

COPY . .