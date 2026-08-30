#!/bin/sh
set -eu

envsubst '${BACKEND_UPSTREAM} ${BACKEND_HOST}' \
  < /etc/nginx/backend.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
