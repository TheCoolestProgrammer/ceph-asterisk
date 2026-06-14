"""Парсинг и сериализация Asterisk .conf для static realtime (ast_config)."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.models.ast_conf import AsteriskConf

# Static realtime через extconfig => VIEW ast_config_inst_<id>
# asterisk.conf, modules.conf, logger.conf — только с диска (см. extconfig.conf.sample).
STATIC_REALTIME_CONF_FILES: tuple[str, ...] = (
    # "pjsip.conf",  # на диске; endpoints/auth/aor — dynamic realtime (ps_*)
    "extensions.conf",
    "voicemail.conf",
    "queues.conf",
    "stasis.conf",
    "cdr.conf",
    "cdr_adaptive_odbc.conf",
    "manager.conf",
    "rtp.conf",
    "http.conf",
)

# Bootstrap: не поддерживают static realtime или нужны до подключения ODBC.
DISK_BOOTSTRAP_CONF_FILES: tuple[str, ...] = (
    "asterisk.conf",
    "modules.conf",
    "logger.conf",
    "musiconhold.conf",
    "extconfig.conf",
    "sorcery.conf",
    "res_odbc.conf",
)


def parse_asterisk_ini(content: str) -> list[tuple[str, str, str]]:
    """Возвращает список (category, var_name, var_val)."""
    category = "general"
    rows: list[tuple[str, str, str]] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and "]" in line:
            category = line[1 : line.index("]")].strip()
            continue

        sep = "=>" if "=>" in line else "="
        if sep not in line:
            continue

        var_name, var_val = (part.strip() for part in line.split(sep, 1))
        if ";" in var_val:
            var_val = var_val.split(";", 1)[0].strip()
        if not var_name:
            continue
        rows.append((category, var_name, var_val))

    return rows


def seed_config_from_ini(
    session: Session,
    instance_id: int,
    filename: str,
    content: str,
) -> None:
    """Записывает содержимое .conf в ast_config (static realtime)."""
    parsed = parse_asterisk_ini(content)
    cat_metric = 0
    var_metric = 0
    prev_category: str | None = None

    for category, var_name, var_val in parsed:
        if category != prev_category:
            cat_metric += 1
            var_metric = 0
            prev_category = category
        var_metric += 1
        session.add(
            AsteriskConf(
                instance_id=instance_id,
                filename=filename,
                category=category,
                var_name=var_name,
                var_val=var_val,
                cat_metric=cat_metric,
                var_metric=var_metric,
            )
        )


def _format_config_line(row: AsteriskConf) -> str:
    if row.filename == "extensions.conf" and row.var_name == "exten":
        return f"exten => {row.var_val}"
    if (
        row.filename == "voicemail.conf"
        and row.category not in ("general", "zonemessages")
    ):
        return f"{row.var_name} => {row.var_val}"
    use_arrow = (
        row.filename == "asterisk.conf"
        and row.category == "directories"
    ) or (
        row.filename == "logger.conf"
        and row.category == "logfiles"
    ) or (row.filename == "modules.conf" and row.var_name == "load")
    sep = " => " if use_arrow else " = "
    return f"{row.var_name}{sep}{row.var_val}"


class _IniRowView:
    """Минимальный вид строки ast_config для сборки .conf из снапшота истории."""

    __slots__ = ("filename", "category", "var_name", "var_val", "cat_metric", "var_metric")

    def __init__(self, data: dict, default_filename: str) -> None:
        self.filename = data.get("filename", default_filename)
        self.category = str(data.get("category", "general"))
        self.var_name = str(data["var_name"])
        self.var_val = str(data["var_val"])
        self.cat_metric = int(data.get("cat_metric", 0))
        self.var_metric = int(data.get("var_metric", 0))


def snapshot_rows_to_ini_content(rows: list[dict], filename: str) -> str:
    """Собирает текст .conf из JSON-снапшота ast_config_history."""
    ordered = sorted(
        [_IniRowView(row, filename) for row in rows],
        key=lambda row: (row.cat_metric, row.var_metric),
    )
    return rows_to_ini_content(ordered)


def rows_to_ini_content(rows: Sequence[AsteriskConf | _IniRowView]) -> str:
    """Собирает текст .conf из строк ast_config."""
    lines: list[str] = []
    prev_category: str | None = None

    for row in rows:
        if row.category != prev_category:
            lines.append(f"[{row.category}]")
            prev_category = row.category
        lines.append(_format_config_line(row))

    return "\n".join(lines) + ("\n" if lines else "")


def replace_config_from_ini(
    session: Session,
    instance_id: int,
    filename: str,
    content: str,
) -> None:
    """Полностью заменяет строки файла в ast_config."""
    session.query(AsteriskConf).filter(
        AsteriskConf.instance_id == instance_id,
        AsteriskConf.filename == filename,
    ).delete(synchronize_session=False)
    seed_config_from_ini(session, instance_id, filename, content)
