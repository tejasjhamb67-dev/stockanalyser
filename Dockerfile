# stockanalyser — web app image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# deps first for layer caching
COPY pyproject.toml README.md ./
COPY src ./src
COPY docs ./docs

RUN pip install --upgrade pip && pip install ".[web,live,db]"

EXPOSE 8000

# honour the platform's $PORT (Render/Railway/Fly set it); default 8000
CMD ["sh", "-c", "uvicorn stockanalyser.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
