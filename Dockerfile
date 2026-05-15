FROM python:3.13-slim AS builder

LABEL org.opencontainers.image.authors="steder@gmail.com"
LABEL version="2.0"

ENV ENV=development \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends \
        build-essential \
        imagemagick \
        git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

FROM builder AS giraffe

EXPOSE 9876

WORKDIR /opt/app

COPY pyproject.toml uv.lock /opt/app/
RUN uv sync --frozen --no-dev --no-install-project

COPY . /opt/app

CMD ["uv", "run", "--no-dev", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "etc/gunicorn.conf.py", "giraffe:app", "--log-level=DEBUG"]

FROM giraffe AS dev
RUN uv sync --frozen

CMD ["uv", "run", "python", "/opt/app/giraffe.py"]
