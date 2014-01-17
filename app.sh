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

#UPDATE THESE
export AWS_ACCESS_KEY_ID="AKIAIS2WMVOQL3APRCBA"
export AWS_SECRET_ACCESS_KEY="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"
export MEMCACHED="cache1a-production.aws.threadless.com:11211;cache1e-production.aws.threadless.com:11211"

/opt/app/env/bin/newrelic-admin run-program /opt/app/env/bin/gunicorn -k gevent -c etc/gunicorn.conf.py giraffe:app --log-level=DEBUG
