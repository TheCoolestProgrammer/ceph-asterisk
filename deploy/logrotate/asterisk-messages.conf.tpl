# Ротация логов всех АТС: asterisk_configs/{name}/asterisk_logs/messages
# copytruncate — Asterisk держит файл открытым; архивы не читает Filebeat (только messages).
/logs/*/asterisk_logs/messages {
    size ${LOG_ROTATE_MAX_SIZE}
    rotate ${LOG_ROTATE_KEEP}
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    dateext
    dateformat -%Y%m%d
}
