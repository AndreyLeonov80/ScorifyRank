# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_PROGRESS_BAR=off

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends busybox-static ca-certificates gcc libc6-dev linux-libc-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install -r /app/requirements.txt

COPY . /app/

EXPOSE 8009

CMD ["/bin/sh", "/app/run.sh"]
