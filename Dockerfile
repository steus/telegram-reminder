FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Сначала только метаданные пакета — для кэширования слоя зависимостей.
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY entrypoint.sh ./

RUN pip install --upgrade pip && pip install . \
    && chmod +x entrypoint.sh \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["./entrypoint.sh"]
