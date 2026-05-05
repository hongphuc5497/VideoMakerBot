FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
# Pin pip for reproducible builds: --upgrade pip==25.x
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install pytest \
    && pip cache purge

RUN python -m playwright install --with-deps chromium

COPY . .

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && chown -R appuser:appuser /app /ms-playwright

RUN chmod +x /app/docker-entrypoint.sh

USER appuser

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
