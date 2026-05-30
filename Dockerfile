FROM python:3.14-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    XDG_CACHE_HOME=/app/.cache

WORKDIR /app

# System deps: ffmpeg for video processing
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch CPU-only first (saves ~1.5GB vs GPU version)
RUN pip install --no-cache-dir torch==2.11.0 --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Install Chromium for Playwright (already cached at /ms-playwright)
RUN python -m playwright install --with-deps chromium

# Clean up pip cache and temp files
RUN pip cache purge 2>/dev/null || true \
    && find /usr/local/lib/python3.14 -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true \
    && find /usr/local/lib/python3.14 -name '*.pyc' -delete 2>/dev/null || true \
    && rm -rf /root/.cache

# Copy app code
COPY . .

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && chown -R appuser:appuser /app /ms-playwright

ENV CLOAKBROWSER_CACHE_DIR=/app/.cache/cloakbrowser
ENV PUBLIC_BASE_PATH=/threads-video-maker
ENV PUBLIC_DEMO_MODE=1

RUN chmod +x /app/docker-entrypoint.sh

USER appuser

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["python", "GUI.py"]
