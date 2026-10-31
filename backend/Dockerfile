# QuoteFlow backend — production image.
#
# Multi-stage so the wheels are built once and the runtime layer stays small,
# and the application runs as an unprivileged user.

# ---- build stage ----------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---- runtime stage --------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    APP_ENV=production \
    DEBUG=false

# curl is only for the container health check below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin quoteflow

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=quoteflow:quoteflow app ./app
COPY --chown=quoteflow:quoteflow scripts ./scripts

# Generated PDFs live here. Mount a volume at this path to keep them across
# deployments; the container writes nothing else.
RUN mkdir -p /app/storage/quotations && chown -R quoteflow:quoteflow /app/storage
VOLUME ["/app/storage"]

USER quoteflow
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# No --reload in production. Workers are processes, so the count comes from the
# host's CPU budget rather than being hard-coded high.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
