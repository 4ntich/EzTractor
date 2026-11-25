FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY eztractor ./eztractor
ARG WITH_WHISPER=1
RUN pip install --no-cache-dir . && if [ "$WITH_WHISPER" = "1" ]; then pip install --no-cache-dir ".[whisper]"; fi

ENV EZT_STORAGE_DIR=/data
EXPOSE 8000
CMD ["uvicorn", "eztractor.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
