# Fábula API — first-deploy image (all stages except the heavy video render).
# ffmpeg = caption duration; fonts-dejavu = thumbnail serif fallback.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

# Persist data under /app/data (Railway disk is ephemeral until Postgres+R2 are wired)
ENV FABULA_DB=/app/data/fabula.db \
    FABULA_OUTPUT=/app/data/output \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
