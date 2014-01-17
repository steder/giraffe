#!/usr/bin/env bash

set -e -u -x

<<EOF

Launch Giraffe

EOF

ROOT=`dirname "$0"`
ROOT=`( cd "$ROOT" && pwd )`

VIRTUALENV=$1

echo "ROOT=$ROOT"

export ENV=production
export NEW_RELIC_CONFIG_FILE="$ROOT/etc/newrelic.ini"

#UPDATE THESE
export AWS_ACCESS_KEY_ID=WHATEVER
export AWS_SECRET_ACCESS_KEY=WHATEVER
export MEMCACHED="WHATEVER1;WHATEVER2"

/opt/app/env/bin/newrelic-admin run-program /opt/app/env/bin/gunicorn -k gevent -c etc/gunicorn.conf.py giraffe:app --log-level=DEBUG
