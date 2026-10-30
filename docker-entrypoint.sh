#!/bin/sh
set -eu

: "${SECRET_KEY:?Set SECRET_KEY to a persistent random secret}"

# Migration failure must prevent the web server from starting.
python -m flask --app 'app:create_app(use_redis=False)' db upgrade
exec "$@"
