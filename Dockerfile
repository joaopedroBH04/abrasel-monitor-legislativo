FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Instalar dependencias do sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar dependencias
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Copiar codigo
COPY src/ src/
COPY config/ config/
COPY migrations/ migrations/
COPY alembic.ini ./

# Instalar playwright browsers (para scraping de assembleias)
RUN playwright install chromium --with-deps || true

# Health check
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python -c "import abrasel_monitor; print('ok')"

# Entrypoint
ENTRYPOINT ["abrasel-monitor"]
CMD ["collect", "camara", "--mode", "incremental"]
