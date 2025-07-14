FROM python:3.13-slim as builder

# metadata
MAINTAINER steder@gmail.com
LABEL version="1.0"

ENV ENV=development

# actual container setup:
RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y --no-install-recommends \
        build-essential \
        imagemagick \
        git \
    && pip install poetry \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

FROM builder as giraffe

# Giraffe listens on 9876 by default
EXPOSE 9876

# let's get the code!

WORKDIR /opt/app

COPY pyproject.toml poetry.lock /opt/app/
RUN poetry install --no-root --without=dev

COPY . /opt/app

RUN poetry install --without=dev

CMD ["poetry", "run", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-c", "etc/gunicorn.conf.py", "giraffe:app", "--log-level=DEBUG"]

FROM giraffe as dev
RUN poetry install

CMD ["poetry", "run", "python", "/opt/app/giraffe.py"]
