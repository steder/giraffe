FROM python:3.8 as builder

# metadata
MAINTAINER steder@gmail.com
LABEL version="1.0"

ENV ENV=development

# actual container setup:
RUN apt-get update \
    && apt-get -y upgrade \
    && apt-get install -y build-essential \
    && apt-get install -y imagemagick \
    git \
    python \
    python-dev \
    python-pip \
    && pip install poetry \
    && rm -rf /var/lib/apt/lists/*

FROM builder as giraffe

# Giraffe listens on 9876 by default
EXPOSE 9876

# let's get the code!

WORKDIR /opt/app

COPY pyproject.toml poetry.lock /opt/app/
RUN poetry install --no-root --no-dev

COPY . /opt/app

RUN poetry install --no-dev

CMD ["poetry", "gunicorn", "-k", "gevent", "-c", "etc/gunicorn.conf.py", "giraffe:app", "--log-level=DEBUG"]

from giraffe as dev
RUN poetry install

CMD ["poetry", "run", "python", "/opt/app/giraffe.py"]
