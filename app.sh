#!/usr/bin/env bash

set -e -u -x

<<EOF

Launch Giraffe (Modern ASGI version)

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

# Option 1: Gunicorn with Uvicorn workers (Recommended for production)
# poetry run newrelic-admin run-program gunicorn -k uvicorn.workers.UvicornWorker -c etc/gunicorn.conf.py giraffe:app --log-level=DEBUG

# Option 2: Direct Uvicorn (Simple, but less process management)
poetry run newrelic-admin run-program uvicorn giraffe:app --host 0.0.0.0 --port 8080 --workers 4 --log-level debug

# Option 3: Hypercorn (For HTTP/3 support)
# poetry run newrelic-admin run-program hypercorn giraffe:app --bind 0.0.0.0:8080 --workers 4 --log-level debug

# Option 4: Granian (Maximum performance)
# poetry run newrelic-admin run-program granian --interface asgi giraffe:app --host 0.0.0.0 --port 8080 --workers 4 