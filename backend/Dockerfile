FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DATASET_ROOT=/data/datasets SPARK_LOCAL_IP=127.0.0.1 PYSPARK_PYTHON=python3
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends default-jre-headless \
    && rm -rf /var/lib/apt/lists/*
FROM runtime AS application
COPY backend/requirements.lock /app/requirements.lock
RUN pip install -r requirements.lock && useradd --create-home --uid 10001 app \
    && mkdir -p /data/datasets /app/.pytest_cache && chown -R app:app /data /app/.pytest_cache
COPY backend/requirements-rules.lock /app/requirements-rules.lock
RUN pip install --timeout 120 -r /app/requirements-rules.lock
COPY --chown=app:app backend /app/backend
COPY --chown=app:app samples /app/samples
COPY --chown=app:app scripts /app/scripts
COPY --chown=app:app deploy /app/deploy
COPY --chown=app:app pytest.ini /app/pytest.ini
WORKDIR /app/backend
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30", "--access-logfile", "-"]
