FROM mcr.microsoft.com/devcontainers/rust@sha256:4b356e56d256b8e835c7e08b2aef302cc92b7c459e5705ac36a6e6d090955f00

USER root

# Install the runtime families required by the fixed validator. Node 24 is
# provided as a binary by actions/setup-node and copied into the build context
# by the trusted workflow; this avoids a second Docker Hub image pull.
COPY toolchain/node /usr/local/bin/node
RUN chmod 0755 /usr/local/bin/node

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
       ca-certificates git python3 python-is-python3 python3-dev python3-venv python3-pip build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir "pytest>=8,<9" "cryptography==50.0.2" \
    && node --version \
    && rustc --version

ENV PATH="/opt/venv/bin:/usr/local/cargo/bin:/usr/local/bin:/usr/bin:/bin" \
    HOME="/tmp" \
    TMPDIR="/tmp" \
    LANG="C.UTF-8" \
    LC_ALL="C.UTF-8" \
    PYTHONUNBUFFERED="1" \
    PYTHONNOUSERSITE="1" \
    PYTHONDONTWRITEBYTECODE="1" \
    CI="true"

WORKDIR /workspace
