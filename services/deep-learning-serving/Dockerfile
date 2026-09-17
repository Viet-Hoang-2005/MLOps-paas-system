FROM python:3.10-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libpq-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --prefix=/install -r /app/requirements.txt

FROM python:3.10-slim

WORKDIR /app

ENV LOG_FORMAT=console \
    LOG_SUMMARY_INTERVAL_SECONDS=60

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY . .
RUN mkdir -p /app/libs

ENV PYTHONPATH=/app/libs:/app
ENV BENTOML_PORT=5002
EXPOSE 5002

CMD ["bentoml", "serve", "src.main:DeepLearningModelService", "--port", "5002", "--host", "0.0.0.0"]
