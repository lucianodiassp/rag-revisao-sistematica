FROM pgvector/pgvector:pg16 AS postgres-client

FROM python:3.11-slim-bookworm

ARG APP_UID=1000
ARG APP_GID=1000

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata \
    OMP_THREAD_LIMIT=2 \
    PATH=/usr/lib/postgresql/16/bin:${PATH}

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        gosu \
        libpq5 \
        libreadline8 \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-por \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

# A versão muda a cada release e não deve invalidar a camada pesada de dependências.
COPY VERSION ./VERSION

# Usa as mesmas ferramentas principais do PostgreSQL do servidor (pg16).
# Evita dumps criados por um cliente mais novo que o banco e incompatíveis na restauração.
COPY --from=postgres-client /usr/lib/postgresql/16/bin /usr/lib/postgresql/16/bin

COPY backend ./backend
COPY frontend ./frontend
COPY database/scripts ./database/scripts
COPY docker/entrypoint.sh /usr/local/bin/rag-entrypoint

RUN mkdir -p /app/data/pdfs /app/data/private /app/data/backups \
    && groupadd --gid "${APP_GID}" ragapp \
    && useradd --create-home --uid "${APP_UID}" --gid "${APP_GID}" ragapp \
    && chown -R ragapp:ragapp /app \
    && chmod 0755 /usr/local/bin/rag-entrypoint

EXPOSE 8501

ENTRYPOINT ["/usr/local/bin/rag-entrypoint"]

CMD ["python", "-m", "streamlit", "run", "frontend/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
