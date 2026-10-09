FROM rust:bookworm

# Install the exact runtime families required by the fixed validator. Candidate
# code is never executed during this image build; only this protected Dockerfile
# and public package repositories are involved.
COPY --from=node:24-bookworm-slim /usr/local/ /usr/local/

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
       ca-certificates git python3 python3-dev python3-venv python3-pip build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir "pytest>=8,<9" "cryptography==50.0.2"

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
