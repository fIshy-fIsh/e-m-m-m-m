FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml README.md .env.example ./
COPY app ./app
COPY docs ./docs
COPY scripts ./scripts
COPY tests ./tests
COPY specs ./specs

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .[dev]

CMD ["python", "-m", "app.jobs.scheduler"]
