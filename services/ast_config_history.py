import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer

from models.ast_conf import AsteriskConf
from models.ast_conf_history import AsteriskConfigHistory

MANAGER_CONF_FILENAME = "manager.conf"

# Поля строки ast_config, которые попадают в снапшот (без id — при откате создаются новые).
_SNAPSHOT_ROW_KEYS = (
    "cat_metric",
    "var_metric",
    "filename",
    "category",
    "var_name",
    "var_val",
    "commented",
)


def _row_to_snapshot_dict(row: AsteriskConf) -> dict[str, Any]:
    return {key: getattr(row, key) for key in _SNAPSHOT_ROW_KEYS}


def _build_snapshot(rows: list[AsteriskConf]) -> str:
    # Снапшот — JSON-массив строк в порядке cat_metric, var_metric.
    # Такой же порядок использует Asterisk static realtime при сборке виртуального .conf.
    # id строк не сохраняем: при откате в «горячей» таблице появятся новые записи.
    payload = [_row_to_snapshot_dict(row) for row in rows]
    return json.dumps(payload, ensure_ascii=False)


def _parse_snapshot(config_snapshot: str) -> list[dict[str, Any]]:
    data = json.loads(config_snapshot)
    if not isinstance(data, list):
        raise ValueError("config_snapshot must be a JSON array of row objects")
    return data


def _next_version(
    session: Session, instance_id: int, filename: str
) -> int:
    current_max = session.scalar(
        select(func.max(AsteriskConfigHistory.version)).where(
            AsteriskConfigHistory.instance_id == instance_id,
            AsteriskConfigHistory.filename == filename,
        )
    )
    return (current_max or 0) + 1


def save_file_version(
    session: Session,
    instance_id: int,
    filename: str,
    description: str | None,
    author: str,
    *,
    commit: bool = True,
) -> AsteriskConfigHistory:
    """
    Сохраняет снимок текущего «горячего» файла в историю.

    1. Читает все строки ast_config для (instance_id, filename).
    2. Сериализует их в JSON (порядок как в realtime).
    3. Назначает следующий номер version для этой пары (АТС, файл).
    """
    rows = (
        session.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == filename,
        )
        .order_by(AsteriskConf.cat_metric, AsteriskConf.var_metric)
        .all()
    )

    version = _next_version(session, instance_id, filename)
    history_entry = AsteriskConfigHistory(
        instance_id=instance_id,
        filename=filename,
        version=version,
        config_snapshot=_build_snapshot(rows),
        description=description,
        author=author,
    )
    session.add(history_entry)
    if commit:
        session.commit()
        session.refresh(history_entry)
    else:
        session.flush()
    return history_entry


def rollback_to_version(session: Session, history_id: int) -> list[AsteriskConf]:
    """
    Откатывает «горячий» ast_config к состоянию из холодного снапшота.

    1. Загружает запись истории по history_id.
    2. Удаляет все текущие строки этого файла для данной АТС.
    3. Вставляет строки из JSON-снапшота (новые id).
    """
    history_entry = session.get(AsteriskConfigHistory, history_id)
    if history_entry is None:
        raise ValueError(f"History record {history_id} not found")

    instance_id = history_entry.instance_id
    filename = history_entry.filename
    snapshot_rows = _parse_snapshot(history_entry.config_snapshot)

    # Полная замена «горячих» строк файла: ast_config должна содержать только актуальное состояние.
    session.query(AsteriskConf).filter(
        AsteriskConf.instance_id == instance_id,
        AsteriskConf.filename == filename,
    ).delete(synchronize_session=False)

    restored: list[AsteriskConf] = []
    # Восстанавливаем строки из снапшота; Asterisk через VIEW увидит их после commit/reload.
    for row_data in snapshot_rows:
        row_filename = row_data.get("filename", filename)
        conf_row = AsteriskConf(
            instance_id=instance_id,
            cat_metric=int(row_data.get("cat_metric", 0)),
            var_metric=int(row_data.get("var_metric", 0)),
            filename=row_filename,
            category=str(row_data.get("category", "general")),
            var_name=str(row_data["var_name"]),
            var_val=str(row_data["var_val"]),
            commented=int(row_data.get("commented", 0)),
        )
        session.add(conf_row)
        restored.append(conf_row)

    session.commit()
    for row in restored:
        session.refresh(row)
    return restored


def apply_manager_ami_port_change(
    session: Session,
    instance_id: int,
    old_ami_port: int,
    new_ami_port: int,
    author: str,
) -> AsteriskConf:
    """
    Перед сменой AMI-порта сохраняет текущий manager.conf в холодное хранилище,
    затем обновляет строку port в «горячей» ast_config.
    """
    save_file_version(
        session,
        instance_id,
        MANAGER_CONF_FILENAME,
        f"ami_port: {old_ami_port} -> {new_ami_port}",
        author,
        commit=False,
    )

    port_rows = (
        session.query(AsteriskConf)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == MANAGER_CONF_FILENAME,
            AsteriskConf.category == "general",
            AsteriskConf.var_name == "port",
        )
        .all()
    )
    if not port_rows:
        session.rollback()
        raise ValueError(
            f"manager.conf [general] port not found for instance_id={instance_id}"
        )

    port_value = str(int(new_ami_port))
    for port_row in port_rows:
        port_row.var_val = port_value

    session.commit()
    session.refresh(port_rows[0])
    return port_rows[0]


def get_file_history(
    session: Session, instance_id: int, filename: str
) -> list[AsteriskConfigHistory]:
    """
    Список версий файла без загрузки тяжёлого config_snapshot.
    """
    return (
        session.query(AsteriskConfigHistory)
        .options(defer(AsteriskConfigHistory.config_snapshot))
        .filter(
            AsteriskConfigHistory.instance_id == instance_id,
            AsteriskConfigHistory.filename == filename,
        )
        .order_by(AsteriskConfigHistory.version.desc())
        .all()
    )
