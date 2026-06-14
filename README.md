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

При старте `fastapi-dev` / `fastapi-prod` скрипт `deploy/entrypoint.sh`:
1. ждёт готовности MySQL;
2. выполняет `alembic upgrade head` (обе БД);
3. запускает uvicorn.

## Миграции (Alembic)

Проект использует две базы MySQL:
- **main** (`MYSQL_DATABASE`) — пользователи, инстансы Asterisk, аудиофайлы;
- **cdr** (`MYSQL_DATABASE_CDR`) — PJSIP, CDR, конфиги Asterisk.

Ветки миграций: `migrations/versions/main/` и `migrations/versions/cdr/`.

```bash
# Применить все миграции (локально или в контейнере)
uv run alembic -x db=main upgrade main@head
uv run alembic -x db=cdr upgrade cdr@head

# Создать новую миграцию после изменения моделей
uv run alembic -x db=main revision --autogenerate -m "описание"
uv run alembic -x db=cdr revision --autogenerate -m "описание"

# Текущие версии
uv run alembic heads
uv run alembic -x db=main current
uv run alembic -x db=cdr current
```

Если таблицы уже созданы через старый `create_all`, один раз отметьте текущую схему без применения DDL:

```bash
uv run alembic -x db=main stamp main@head
uv run alembic -x db=cdr stamp cdr@head
```
