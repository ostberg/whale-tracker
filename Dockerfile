# The Whale Tracker job image (W-042). One image for every job; the job's arguments pick the work:
#   collect sec --apply                 scheduled, as id-whales-ingest (the only job that reads the internet)
#   config sync --apply | db migrate --apply | status      the admin job, as id-whales-admin
#
# Built by infra/deploy.py from `git archive HEAD`, so only committed files can enter it (never .env).
# Base pinned by digest, the same python:3.13-slim the Tamale repo vetted (2026-09-02); bump deliberately.
FROM python:3.13-slim@sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285

ARG GIT_SHA=unknown
LABEL org.opencontainers.image.title="whale-tracker" \
      org.opencontainers.image.description="Whale Tracker: managers' letters and public filings" \
      org.opencontainers.image.revision="${GIT_SHA}"

ENV GIT_SHA=${GIT_SHA} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    WHALES_CONFIG_DIR=/app/config

WORKDIR /app

# Dependencies only from the hash-pinned lock: a substituted file at the same version is refused.
COPY requirements-runtime.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-runtime.lock

# The code runs from source (PYTHONPATH), so no package build pulls an unpinned setuptools.
COPY src ./src
COPY config ./config

RUN useradd --create-home --uid 10001 appuser
USER appuser

# No credentials inside: the database token comes from the job's managed identity at run time.
ENTRYPOINT ["python", "-m", "whales"]
CMD ["--help"]
