#!/usr/bin/env bash

set -e -u -x

echo "Installing upstart config..."
ln -s etc/upstart.conf /etc/init/giraffe.conf

echo "Updating upstart configuration..."
initctl reload-configuration

echo "Next Steps"
echo "1. Create your virtualenv at '/home/ubuntu/.virtualenvs/giraffe'"
echo "2. install your requirements: pip install -r requirements.txt"
echo "3. update your app.sh AWS_* environment variables and BUCKET*"
echo "4. start things up: sudo service giraffe start"
