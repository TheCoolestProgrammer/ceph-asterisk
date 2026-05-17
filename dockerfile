# Пример для ручной сборки. Образ инстансов API: docker/asterisk.Dockerfile.
FROM andrius/asterisk:latest

USER root

RUN apt-get update && apt-get install -y \
    unixodbc \
    odbc-mariadb \
    && rm -rf /var/lib/apt/lists/*

USER asterisk