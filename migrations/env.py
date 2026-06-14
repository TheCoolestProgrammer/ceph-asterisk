"""Alembic env: две независимые ветки миграций (main и cdr)."""

import logging
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import config as app_config
from app.core.database import Base, BaseCDR

import app.models  # noqa: F401 — регистрация моделей в metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")

MIGRATIONS_ROOT = Path(__file__).resolve().parent

DATABASES: dict[str, dict] = {
    "main": {
        "url": app_config.DATABASE_URL,
        "metadata": Base.metadata,
        "version_table": "alembic_version",
    },
    "cdr": {
        "url": app_config.DATABASE_CDR_URL,
        "metadata": BaseCDR.metadata,
        "version_table": "alembic_version_cdr",
    },
}


def _get_target_db() -> str | None:
    return context.get_x_argument(as_dictionary=True).get("db")


def _run_migrations(db_name: str) -> None:
    db = DATABASES[db_name]
    version_locations = [str(MIGRATIONS_ROOT / "versions" / db_name)]

    if context.is_offline_mode():
        context.configure(
            url=db["url"],
            target_metadata=db["metadata"],
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            version_table=db["version_table"],
            version_locations=version_locations,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = create_engine(db["url"], poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=db["metadata"],
            version_table=db["version_table"],
            version_locations=version_locations,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    target_db = _get_target_db()
    databases = [target_db] if target_db else list(DATABASES)
    for db_name in databases:
        _run_migrations(db_name)


def run_migrations_online() -> None:
    target_db = _get_target_db()
    databases = [target_db] if target_db else list(DATABASES)
    for db_name in databases:
        logger.info("Applying migrations for database: %s", db_name)
        _run_migrations(db_name)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
