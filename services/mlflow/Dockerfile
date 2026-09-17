FROM ghcr.io/mlflow/mlflow:v2.14.1

WORKDIR /app

COPY requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --default-timeout=100 --retries=5 -r requirements.txt
