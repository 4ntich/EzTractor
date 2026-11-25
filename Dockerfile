# ---------- 1) site (Next.js exportado como arquivos estáticos)
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---------- 2) app (API + processamento de vídeo + site)
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/eztractor ./eztractor
RUN pip install --no-cache-dir ".[whisper]"
COPY --from=web /web/out /app/web

ENV EZT_WEB_DIR=/app/web \
    EZT_FONTS_DIR=/app/web/fonts \
    EZT_STORAGE_DIR=/data/media \
    EZT_DATABASE_URL=sqlite:////data/eztractor.db \
    EZT_QUEUE_MODE=inline \
    HF_HOME=/data/models \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://localhost:8000/health || exit 1
CMD ["uvicorn", "eztractor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
