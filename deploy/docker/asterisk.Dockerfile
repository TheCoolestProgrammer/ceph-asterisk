# Звуки собираем в отдельном stage на том же базовом образе,
# чтобы не тянуть дополнительный alpine при проблемах с Docker Hub.
FROM andrius/asterisk:latest AS sounds

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    ca-certificates \
    tar \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /out/en \
    && wget -q --tries=5 --timeout=30 -O /tmp/core-sounds-ulaw.tar.gz \
        "https://downloads.asterisk.org/pub/telephony/sounds/asterisk-core-sounds-en-ulaw-current.tar.gz" \
    && tar -xzf /tmp/core-sounds-ulaw.tar.gz -C /out/en \
    && (wget -q --tries=5 --timeout=30 -O /tmp/extra-sounds-ulaw.tar.gz \
        "https://downloads.asterisk.org/pub/telephony/sounds/releases/asterisk-extra-sounds-en-ulaw-1.5.2.tar.gz" \
        || wget -q --tries=5 --timeout=30 -O /tmp/extra-sounds-ulaw.tar.gz \
        "https://downloads.asterisk.org/pub/telephony/sounds/asterisk-extra-sounds-en-ulaw-current.tar.gz" \
        || wget -q --tries=5 --timeout=30 -O /tmp/extra-sounds-ulaw.tar.gz \
        "https://downloads.asterisk.org/pub/telephony/sounds/releases/asterisk-extra-sounds-en-ulaw-current.tar.gz" \
        || wget -q --tries=5 --timeout=30 -O /tmp/extra-sounds-ulaw.tar.gz \
        "http://downloads.asterisk.org/pub/telephony/sounds/asterisk-extra-sounds-en-ulaw-current.tar.gz" \
        || wget -q --tries=5 --timeout=30 -O /tmp/extra-sounds-ulaw.tar.gz \
        "http://downloads.asterisk.org/pub/telephony/sounds/releases/asterisk-extra-sounds-en-ulaw-current.tar.gz") \
    && tar -xzf /tmp/extra-sounds-ulaw.tar.gz -C /out/en \
    && rm -f /tmp/core-sounds-ulaw.tar.gz \
    && rm -f /tmp/extra-sounds-ulaw.tar.gz \
    && test -f /out/en/vm-intro.ulaw \
    && test -f /out/en/vm-password.ulaw \
    && ls -la /out/en/vm-intro.ulaw /out/en/vm-password.ulaw

FROM andrius/asterisk:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    odbc-mariadb \
    && rm -rf /var/lib/apt/lists/*

COPY --from=sounds /out/en /opt/asterisk-core-sounds/en
COPY --from=sounds /out/en /var/lib/asterisk/sounds/en

RUN chown -R asterisk:asterisk /opt/asterisk-core-sounds \
    && chown -R asterisk:asterisk /var/lib/asterisk/sounds \
    && chmod -R a+rX /opt/asterisk-core-sounds \
    && chmod -R a+rX /var/lib/asterisk/sounds \
    && test -f /opt/asterisk-core-sounds/en/vm-intro.ulaw \
    && test -f /opt/asterisk-core-sounds/en/vm-password.ulaw \
    && test -f /var/lib/asterisk/sounds/en/vm-intro.ulaw \
    && test -f /var/lib/asterisk/sounds/en/vm-password.ulaw

USER asterisk
