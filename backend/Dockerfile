FROM mwader/static-ffmpeg:7.1.1@sha256:11a44711684c0b9f754c047dcd64235b8b52deab251bd0e0a86f22faa160749c AS media-tools

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=media-tools /ffprobe /usr/local/bin/ffprobe
COPY --from=media-tools /ffmpeg /usr/local/bin/ffmpeg
RUN groupadd --system --gid 10001 mentoring \
    && useradd --system --uid 10001 --gid mentoring --home-dir /nonexistent mentoring \
    && mkdir -p /tmp/interview-staging /var/lib/mentoring/interview-legacy-transcode \
    && chown mentoring:mentoring \
        /tmp/interview-staging \
        /var/lib/mentoring/interview-legacy-transcode
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

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
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
