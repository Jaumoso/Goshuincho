# syntax=docker/dockerfile:1

FROM node:26-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    FRONTEND_DIST=/app/frontend \
    STATIC_ROOT=/app/staticfiles \
    MEDIA_ROOT=/data/media
RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 1000 --home /app goshuincho \
    && mkdir -p /data/media /data/tiles \
    && chown -R goshuincho /data
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY --from=frontend /src/dist /app/frontend
RUN SECRET_KEY=build python manage.py collectstatic --noinput -v0
ARG GOSHUINCHO_VERSION=dev
ENV GOSHUINCHO_VERSION=$GOSHUINCHO_VERSION
USER goshuincho
EXPOSE 8000
CMD ["gunicorn", "goshuincho.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]

FROM runtime AS test
USER root
RUN uv sync --frozen --no-install-project
USER goshuincho
CMD ["pytest", "-q"]
