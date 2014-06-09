#!/usr/bin/env bash

set -e -u -x

<<EOF

Launch Giraffe

EOF

ROOT=`dirname "$0"`
ROOT=`( cd "$ROOT" && pwd )`

echo "ROOT=$ROOT"

echo "Loading ec2metadata..."

`ec2metadata --user-data`

export ENV=$CLOUD_DEV_PHASE
export NEW_RELIC_CONFIG_FILE="$ROOT/etc/newrelic.ini"
export NEW_RELIC_ENVIRONMENT=$CLOUD_DEV_PHASE

if [ -e $ROOT/conf.sh ]; then
    source $ROOT/conf.sh
fi

/opt/app/env/bin/newrelic-admin run-program /opt/app/env/bin/gunicorn -k gevent -c etc/gunicorn.conf.py giraffe:app --log-level=DEBUG
