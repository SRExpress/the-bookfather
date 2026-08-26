# The Bookfather search API - lightweight image, no dataset baked in.
# The multi-GB SQLite DB and raw sources live entirely on a mounted volume (see
# docker/compose/docker-compose-sys-01.yaml) so this image only ever contains code + dependencies.
#
# Build context is the project root (see the compose file's `context: ../..`), since COPY
# below needs requirements.txt and src/ from there - this Dockerfile cannot be built standalone
# with `docker build docker/api`.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
