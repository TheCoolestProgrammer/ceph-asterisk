"""Совместимость таблиц ps_* со схемой Asterisk realtime (ODBC)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

# Колонки, которые Asterisk 18–22 может запрашивать через SELECT * / WHERE.
PS_ENDPOINTS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("mailboxes", "VARCHAR(80) NULL"),
    ("devicestate_busy_at", "INT NULL"),
    ("voicemail_extension", "VARCHAR(40) NULL"),
    ("mohsuggest", "VARCHAR(40) NULL"),
    ("dtmfmode", "VARCHAR(16) NULL"),
    ("outbound_auth", "VARCHAR(40) NULL"),
    ("outbound_proxy", "VARCHAR(40) NULL"),
    ("rewrite_contact", "VARCHAR(8) NULL"),
    ("rtp_symmetric", "VARCHAR(8) NULL"),
    ("force_rport", "VARCHAR(8) NULL"),
    ("direct_media", "VARCHAR(8) NULL"),
    ("connected_line_method", "VARCHAR(16) NULL"),
    ("direct_media_method", "VARCHAR(16) NULL"),
    ("ice_support", "VARCHAR(8) NULL"),
    ("media_encryption", "VARCHAR(16) NULL"),
    ("timers", "VARCHAR(16) NULL"),
    ("send_pai", "VARCHAR(8) NULL"),
    ("send_rpid", "VARCHAR(8) NULL"),
    ("trust_id_inbound", "VARCHAR(8) NULL"),
    ("trust_id_outbound", "VARCHAR(8) NULL"),
    ("aggregate_mwi", "VARCHAR(8) NULL"),
    ("allow_subscribe", "VARCHAR(8) NULL"),
    ("sub_min_expiry", "INT NULL"),
    ("fromdomain", "VARCHAR(40) NULL"),
    ("fromuser", "VARCHAR(40) NULL"),
    ("mwi_fromuser", "VARCHAR(40) NULL"),
)

PS_AORS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("contact", "VARCHAR(255) NULL"),
    ("mailboxes", "VARCHAR(80) NULL"),
    ("remove_existing", "VARCHAR(8) NULL"),
    ("authenticate_qualify", "VARCHAR(8) NULL"),
)

PS_AUTHS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("realm", "VARCHAR(40) NULL"),
    ("nonce_lifetime", "INT NULL"),
    ("md5_cred", "VARCHAR(40) NULL"),
)

PS_CONTACTS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("endpoint", "VARCHAR(40) NULL"),
    ("user_agent", "VARCHAR(255) NULL"),
    ("qualify_timeout", "FLOAT NULL"),
    ("reg_server", "VARCHAR(60) NULL"),
)


def _column_exists(db_cdr: Session, table: str, column: str) -> bool:
    row = db_cdr.execute(
        text(
            """
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = :table
              AND COLUMN_NAME = :column
            """
        ),
        {"table": table, "column": column},
    ).scalar()
    return bool(row)


def _add_column_if_missing(
    db_cdr: Session, table: str, column: str, ddl: str
) -> bool:
    if _column_exists(db_cdr, table, column):
        return False
    db_cdr.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    return True


def ensure_pjsip_schema(db_cdr: Session) -> list[str]:
    """Добавляет отсутствующие колонки ps_* для ODBC realtime. Возвращает список добавленных."""
    added: list[str] = []
    for table, columns in (
        ("ps_endpoints", PS_ENDPOINTS_COLUMNS),
        ("ps_aors", PS_AORS_COLUMNS),
        ("ps_auths", PS_AUTHS_COLUMNS),
        ("ps_contacts", PS_CONTACTS_COLUMNS),
    ):
        for column, ddl in columns:
            if _add_column_if_missing(db_cdr, table, column, ddl):
                added.append(f"{table}.{column}")
    if added:
        db_cdr.commit()
    return added
