FROM ubuntu:16.04

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
    && pip install virtualenv \
    && rm -rf /var/lib/apt/lists/*

# Giraffe listens on 9876 by default
EXPOSE 9876

# let's get the code!

WORKDIR /opt/app
COPY . /opt/app

# Install app dependencies:

RUN virtualenv /opt/app/env && \
    /opt/app/env/bin/pip install -r /opt/app/requirements.txt

# GO GO GO!

CMD ["/opt/app/env/bin/python", "/opt/app/giraffe.py"]
