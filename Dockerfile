FROM python:3.11-slim

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN apt-get update \
    && apt-get install --yes --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY docker/entrypoint.sh /usr/local/bin/rag-entrypoint

RUN mkdir -p /app/data/pdfs /app/data/private \
    && groupadd --gid "${APP_GID}" ragapp \
    && useradd --create-home --uid "${APP_UID}" --gid "${APP_GID}" ragapp \
    && chown -R ragapp:ragapp /app \
    && chmod 0755 /usr/local/bin/rag-entrypoint

EXPOSE 8501

ENTRYPOINT ["/usr/local/bin/rag-entrypoint"]

CMD ["python", "-m", "streamlit", "run", "frontend/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
