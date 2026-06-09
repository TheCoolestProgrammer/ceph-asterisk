#!/bin/sh
set -eu

export LOG_ROTATE_MAX_SIZE="${LOG_ROTATE_MAX_SIZE:-50M}"
export LOG_ROTATE_KEEP="${LOG_ROTATE_KEEP:-3}"
export LOG_ROTATE_INTERVAL_SEC="${LOG_ROTATE_INTERVAL_SEC:-900}"

envsubst '${LOG_ROTATE_MAX_SIZE} ${LOG_ROTATE_KEEP}' \
  < /etc/logrotate.d/asterisk.tpl \
  > /etc/logrotate.d/asterisk

mkdir -p /var/lib/logrotate

while true; do
  logrotate -s /var/lib/logrotate/status /etc/logrotate.d/asterisk
  sleep "${LOG_ROTATE_INTERVAL_SEC}"
done
