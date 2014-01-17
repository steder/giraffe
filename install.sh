#!/usr/bin/env bash

set -e -u -x

sudo mkdir -p /opt
sudo ln -s . /opt/app

echo "Installing upstart config..."
sudo ln -s etc/upstart.conf /etc/init/giraffe.conf

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

