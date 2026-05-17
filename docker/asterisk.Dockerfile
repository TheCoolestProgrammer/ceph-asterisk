FROM andrius/asterisk:latest

USER root

RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    odbc-mariadb \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Промпты только с downloads.asterisk.org (в Debian-репо andrius/asterisk их нет).
# Архив содержит vm-intro.ulaw в корне — распаковка в sounds/en/.
RUN set -eux; \
    SOUNDS=/var/lib/asterisk/sounds; \
    mkdir -p "$SOUNDS/en"; \
    cd /tmp; \
    wget -O core-sounds-ulaw.tar.gz \
        "https://downloads.asterisk.org/pub/telephony/sounds/asterisk-core-sounds-en-ulaw-current.tar.gz"; \
    tar -xzf core-sounds-ulaw.tar.gz -C "$SOUNDS/en"; \
    rm -f core-sounds-ulaw.tar.gz; \
    test -f "$SOUNDS/en/vm-intro.ulaw"

USER asterisk
