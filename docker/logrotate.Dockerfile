FROM alpine:3.21

RUN apk add --no-cache logrotate gettext

COPY deploy/logrotate/asterisk-messages.conf.tpl /etc/logrotate.d/asterisk.tpl
COPY deploy/logrotate/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
