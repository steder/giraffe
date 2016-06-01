FROM alpine

# metadata
MAINTAINER steder@gmail.com
LABEL version="1.0"

ENV ENV=development

# actual container setup:
RUN apk add --update \
    build-base \
    imagemagick \
    git \
    python \
    python-dev \
    py-pip \
    && pip install virtualenv \
    && rm -rf /var/cache/apk/*

# Giraffe listens on 9876 by default
EXPOSE 9876

# let's get the code!

WORKDIR /opt/app
COPY . /opt/app

# Install app dependencies:

RUN virtualenv /opt/app/env && \
    /opt/app/env/bin/pip install -r /opt/app/requirements.txt

# GO GO GO!

CMD /opt/app/env/bin/python /opt/app/giraffe.py
