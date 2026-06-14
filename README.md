# ceph-asterisk

## Структура

```
app/          — Python-приложение (FastAPI)
deploy/       — Docker, compose, init-скрипты, LDAP ldif
asterisk_configs/  — конфиги АТС (runtime)
docker-compose/    — compose-файлы инстансов (генерируются API)
```

## Локальный запуск

```bash
cp .env.compose.example .env
cp .env.mysql.example .env.mysql
cp .env.ldap.example .env.ldap
cp .env.fastapi.example .env.fastapi

uv sync
uv run uvicorn app.main:app --reload
```

## Docker

```bash
cp .env.compose.example .env      # COMPOSE_PROFILES, MYSQL_PORT — для ${VAR} в yaml
cp .env.mysql.example .env.mysql
cp .env.ldap.example .env.ldap
cp .env.fastapi.example .env.fastapi

docker compose --profile dev up
```

`.env` нужен только для подстановок в `docker-compose.yaml` (`${MYSQL_PORT}` и т.д.).
Контейнеры получают переменные из своих `env_file`: `.env.mysql`, `.env.ldap`, `.env.fastapi`.
