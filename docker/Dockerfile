FROM python:3.11-slim-bookworm

WORKDIR /app

# Prisma-specific environment variables
ENV PRISMA_USE_NODEJS_BIN=true
ENV PRISMA_BINARY_PLATFORM=debian-openssl-3.0.x
ENV PRISMA_BINARY_CACHE_DIR=/root/prisma-python

ENV PATH="/root/.cargo/bin/:$PATH"
ENV UV_SYSTEM_PYTHON=true
ENV NVM_DIR=/root/.nvm
ENV NODE_VERSION=v20.11.1
ENV NODE_PATH=$NVM_DIR/versions/node/$NODE_VERSION/lib/node_modules
ENV PATH=$NVM_DIR/versions/node/$NODE_VERSION/bin:$PATH

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential curl git ca-certificates openssl clang libssl-dev llvm libudev-dev make pkg-config protobuf-compiler\
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash \
    && . $NVM_DIR/nvm.sh \
    && nvm install $NODE_VERSION \
    && nvm alias default $NODE_VERSION \
    && nvm use default \
    && npm install -g uglify-js

RUN mkdir -p /root/prisma-python

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv
COPY . .
RUN chmod +x entrypoints.sh

ARG TARGETPLATFORM

RUN echo "Building for TARGETPLATFORM: $TARGETPLATFORM"

RUN git config --global --add safe.directory /app
RUN git config --unset 'http.https://github.com/.extraheader' || true

# jank because pytorch has different versions for cpu for darwin VS linux, see pyproject.toml for specifics
RUN if [ "$TARGETPLATFORM" = "linux/amd64" ]; then \
    uv pip install --no-cache -e . --find-links https://download.pytorch.org/whl/torch_stable.html; \
    else \
    uv pip install --no-cache -e .; \
    fi

ENTRYPOINT ["./entrypoints.sh"]
