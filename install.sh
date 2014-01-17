#!/usr/bin/env bash

set -e -u -x

ROOT=`dirname "$0"`
ROOT=`( cd "$ROOT" && pwd )`

sudo mkdir -p /opt
sudo rm -f /opt/app
sudo ln -s $ROOT /opt/app

echo "Installing upstart config..."
sudo rm -f /etc/init/giraffe.conf
sudo ln -s $ROOT/etc/upstart.conf /etc/init/giraffe.conf

echo "Updating upstart configuration..."
sudo initctl reload-configuration

echo "Next Steps"
echo "1. Create your virtualenv at '/home/ubuntu/.virtualenvs/giraffe'"
mkdir -p /opt/app/
virtualenv /opt/app/env
echo "2. install your requirements: pip install -r requirements.txt"
/opt/app/env/bin/pip install -r requirements.txt
echo "3. update your app.sh AWS_* environment variables and BUCKET*"
echo "4. start things up: sudo service giraffe start"

