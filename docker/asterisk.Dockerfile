# Звуки собираем в отдельном stage (без VOLUME базового образа Asterisk)
FROM alpine:3.20 AS sounds

RUN apk add --no-cache wget tar \
    && mkdir -p /out/en \
    && wget -q -O /tmp/core-sounds-ulaw.tar.gz \
        "https://downloads.asterisk.org/pub/telephony/sounds/asterisk-core-sounds-en-ulaw-current.tar.gz" \
    && tar -xzf /tmp/core-sounds-ulaw.tar.gz -C /out/en \
    && rm -f /tmp/core-sounds-ulaw.tar.gz \
    && test -f /out/en/vm-intro.ulaw \
    && ls -la /out/en/vm-intro.ulaw

FROM andrius/asterisk:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    odbc-mariadb \
    && rm -rf /var/lib/apt/lists/*

COPY --from=sounds /out/en /opt/asterisk-core-sounds/en

RUN chown -R asterisk:asterisk /opt/asterisk-core-sounds \
    && chmod -R a+rX /opt/asterisk-core-sounds \
    && test -f /opt/asterisk-core-sounds/en/vm-intro.ulaw

USER asterisk
