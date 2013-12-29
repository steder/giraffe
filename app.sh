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

$VIRTUALENV/bin/newrelic-admin run-program $VIRTUALENV/bin/gunicorn -k gevent -c etc/gunicorn.conf.py giraffe:app --log-level=DEBUG
