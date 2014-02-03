#!/usr/bin/env bash

set -e -u -x

<<EOF

Launch Giraffe

EOF

ROOT=`dirname "$0"`
ROOT=`( cd "$ROOT" && pwd )`

echo "ROOT=$ROOT"

export ENV=production
export NEW_RELIC_CONFIG_FILE="$ROOT/etc/newrelic.ini"

if [ -e $ROOT/conf.sh ]; then
    source $ROOT/conf.sh
fi

/opt/app/env/bin/newrelic-admin run-program /opt/app/env/bin/gunicorn -k gevent -c etc/gunicorn.conf.py giraffe:app --log-level=DEBUG
