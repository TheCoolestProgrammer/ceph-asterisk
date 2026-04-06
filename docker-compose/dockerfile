FROM andrius/asterisk:latest

# Переключаемся на root для установки
USER root

# Устанавливаем драйверы
RUN apt-get update && apt-get install -y \
    unixodbc \
    odbc-mariadb \
    && rm -rf /var/lib/apt/lists/*

# Возвращаемся к пользователю asterisk (если это предусмотрено образом)
USER asterisk