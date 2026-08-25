FROM mwader/static-ffmpeg:8.1.2@sha256:33f770f812cbfc3de96c547157fc9faf8bd95a36481753439ffa761045167585 AS media-tools

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS dependency-wheels

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        cargo \
        libssl-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
# Recent upstream aarch64 wheels use CPU instructions that are unavailable in
# some Docker Desktop VMs. Build cryptography from its hash-verified sdist for
# the actual build CPU; all remaining packages stay hash-pinned binary wheels.
RUN pip wheel \
        --require-hashes \
        --no-binary=cryptography \
        --wheel-dir=/wheels \
        -r requirements.txt

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=media-tools /ffprobe /usr/local/bin/ffprobe
COPY --from=media-tools /ffmpeg /usr/local/bin/ffmpeg
RUN groupadd --system --gid 10001 mentoring \
    && useradd --system --uid 10001 --gid mentoring --home-dir /nonexistent mentoring \
    && mkdir -p \
        /tmp/interview-staging \
        /var/lib/mentoring/interview-legacy-transcode \
        /var/lib/mentoring/content-media-normalization \
    && chown mentoring:mentoring \
        /tmp/interview-staging \
        /var/lib/mentoring/interview-legacy-transcode \
        /var/lib/mentoring/content-media-normalization
COPY requirements.txt ./
COPY --from=dependency-wheels /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels --no-deps \
        /wheels/cryptography-*.whl \
    && pip install --no-cache-dir --no-index --find-links=/wheels \
        --require-hashes -r requirements.txt \
    && rm -rf /wheels
COPY certs/russian_trusted_root_ca.crt /usr/local/share/ca-certificates/russian_trusted_root_ca.crt
COPY certs/russian_trusted_sub_ca.crt /usr/local/share/ca-certificates/russian_trusted_sub_ca.crt
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM base AS migration
COPY --chown=mentoring:mentoring app ./app
COPY --chown=mentoring:mentoring migrations ./migrations
COPY --chown=mentoring:mentoring alembic.ini ./alembic.ini
USER mentoring
CMD ["alembic", "upgrade", "head"]

FROM base AS runtime
COPY --chown=mentoring:mentoring app ./app
USER mentoring
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=2).read()" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
