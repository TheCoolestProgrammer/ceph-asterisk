"""CRUD очередей Asterisk в static realtime (ast_config / queues.conf)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ast_conf import AsteriskConf
from app.schemas.queue import KNOWN_QUEUE_OPTION_FIELDS, QueueCreate, QueueResponse, QueueUpdate
from app.services.ast_config_history import save_file_version

QUEUES_CONF_FILENAME = "queues.conf"
RESERVED_QUEUE_CATEGORIES = frozenset({"general"})


def _snapshot_queues_before_change(
    db_cdr: Session,
    instance_id: int,
    description: str,
    author: str,
) -> None:
    save_file_version(
        db_cdr,
        instance_id,
        QUEUES_CONF_FILENAME,
        description,
        author,
        commit=False,
    )


def _queue_rows_filter(db_cdr: Session, instance_id: int, queue_name: str | None = None):
    query = db_cdr.query(AsteriskConf).filter(
        AsteriskConf.instance_id == instance_id,
        AsteriskConf.filename == QUEUES_CONF_FILENAME,
    )
    if queue_name is not None:
        query = query.filter(AsteriskConf.category == queue_name)
    return query


def _queue_rows_query(db_cdr: Session, instance_id: int, queue_name: str | None = None):
    return _queue_rows_filter(db_cdr, instance_id, queue_name).order_by(
        AsteriskConf.cat_metric, AsteriskConf.var_metric
    )


def _next_cat_metric(db_cdr: Session, instance_id: int) -> int:
    max_metric = (
        db_cdr.query(AsteriskConf.cat_metric)
        .filter(
            AsteriskConf.instance_id == instance_id,
            AsteriskConf.filename == QUEUES_CONF_FILENAME,
        )
        .order_by(AsteriskConf.cat_metric.desc())
        .limit(1)
        .scalar()
    )
    return (max_metric or 0) + 1


def _rows_to_queue_response(queue_name: str, rows: list[AsteriskConf]) -> QueueResponse:
    members: list[str] = []
    raw_options: dict[str, str] = {}

    for row in rows:
        if row.var_name == "member":
            members.append(row.var_val)
        else:
            raw_options[row.var_name] = row.var_val

    known: dict[str, str | None] = {
        field: raw_options.pop(field, None) for field in KNOWN_QUEUE_OPTION_FIELDS
    }
    return QueueResponse(
        name=queue_name,
        strategy=known.get("strategy"),
        timeout=known.get("timeout"),
        retry=known.get("retry"),
        musicclass=known.get("musicclass"),
        ringinuse=known.get("ringinuse"),
        maxlen=known.get("maxlen"),
        members=members,
        options=raw_options,
    )


def _queue_option_pairs(
    *,
    strategy: str | None = None,
    timeout: int | str | None = None,
    retry: int | str | None = None,
    musicclass: str | None = None,
    ringinuse: str | None = None,
    maxlen: int | str | None = None,
    options: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    field_values: dict[str, object | None] = {
        "strategy": strategy,
        "timeout": timeout,
        "retry": retry,
        "musicclass": musicclass,
        "ringinuse": ringinuse,
        "maxlen": maxlen,
    }
    for field_name, value in field_values.items():
        if value is not None:
            pairs.append((field_name, str(value)))
    if options:
        for key, value in options.items():
            if key in RESERVED_QUEUE_CATEGORIES or key in KNOWN_QUEUE_OPTION_FIELDS:
                continue
            if key == "member":
                continue
            pairs.append((key, value))
    return pairs


def _insert_queue_rows(
    db_cdr: Session,
    instance_id: int,
    queue_name: str,
    *,
    cat_metric: int,
    option_pairs: list[tuple[str, str]],
    members: list[str],
) -> list[AsteriskConf]:
    rows: list[AsteriskConf] = []
    var_metric = 0

    for var_name, var_val in option_pairs:
        var_metric += 1
        row = AsteriskConf(
            instance_id=instance_id,
            filename=QUEUES_CONF_FILENAME,
            category=queue_name,
            var_name=var_name,
            var_val=var_val,
            cat_metric=cat_metric,
            var_metric=var_metric,
        )
        db_cdr.add(row)
        rows.append(row)

    for member in members:
        var_metric += 1
        row = AsteriskConf(
            instance_id=instance_id,
            filename=QUEUES_CONF_FILENAME,
            category=queue_name,
            var_name="member",
            var_val=member,
            cat_metric=cat_metric,
            var_metric=var_metric,
        )
        db_cdr.add(row)
        rows.append(row)

    return rows


def list_queues(db_cdr: Session, instance_id: int) -> list[QueueResponse]:
    rows = _queue_rows_query(db_cdr, instance_id).all()
    by_category: dict[str, list[AsteriskConf]] = {}
    for row in rows:
        if row.category in RESERVED_QUEUE_CATEGORIES:
            continue
        by_category.setdefault(row.category, []).append(row)

    return [
        _rows_to_queue_response(name, category_rows)
        for name, category_rows in sorted(by_category.items())
    ]


def get_queue(db_cdr: Session, instance_id: int, queue_name: str) -> QueueResponse | None:
    rows = _queue_rows_query(db_cdr, instance_id, queue_name).all()
    if not rows:
        return None
    return _rows_to_queue_response(queue_name, rows)


def queue_exists(db_cdr: Session, instance_id: int, queue_name: str) -> bool:
    return (
        _queue_rows_query(db_cdr, instance_id, queue_name)
        .limit(1)
        .first()
        is not None
    )


def create_queue(
    db_cdr: Session,
    instance_id: int,
    data: QueueCreate,
    *,
    author: str = "api",
) -> QueueResponse:
    if queue_exists(db_cdr, instance_id, data.name):
        raise ValueError(f"Queue '{data.name}' already exists")

    _snapshot_queues_before_change(
        db_cdr,
        instance_id,
        f"before create queue '{data.name}'",
        author,
    )

    option_pairs = _queue_option_pairs(
        strategy=data.strategy,
        timeout=data.timeout,
        retry=data.retry,
        musicclass=data.musicclass,
        ringinuse=data.ringinuse,
        maxlen=data.maxlen,
        options=data.options,
    )
    cat_metric = _next_cat_metric(db_cdr, instance_id)
    rows = _insert_queue_rows(
        db_cdr,
        instance_id,
        data.name,
        cat_metric=cat_metric,
        option_pairs=option_pairs,
        members=data.members,
    )
    db_cdr.commit()
    return _rows_to_queue_response(data.name, rows)


def update_queue(
    db_cdr: Session,
    instance_id: int,
    queue_name: str,
    data: QueueUpdate,
    *,
    author: str = "api",
) -> QueueResponse:
    existing_rows = _queue_rows_query(db_cdr, instance_id, queue_name).all()
    if not existing_rows:
        raise LookupError(f"Queue '{queue_name}' not found")

    _snapshot_queues_before_change(
        db_cdr,
        instance_id,
        f"before update queue '{queue_name}'",
        author,
    )

    current = _rows_to_queue_response(queue_name, existing_rows)
    cat_metric = existing_rows[0].cat_metric

    members = current.members if data.members is None else data.members
    strategy = data.strategy if data.strategy is not None else current.strategy
    timeout = data.timeout if data.timeout is not None else current.timeout
    retry = data.retry if data.retry is not None else current.retry
    musicclass = (
        data.musicclass if data.musicclass is not None else current.musicclass
    )
    ringinuse = data.ringinuse if data.ringinuse is not None else current.ringinuse
    maxlen = data.maxlen if data.maxlen is not None else current.maxlen
    options = {**current.options, **(data.options or {})}

    _queue_rows_filter(db_cdr, instance_id, queue_name).delete(
        synchronize_session=False
    )

    option_pairs = _queue_option_pairs(
        strategy=strategy,
        timeout=timeout,
        retry=retry,
        musicclass=musicclass,
        ringinuse=ringinuse,
        maxlen=maxlen,
        options=options,
    )
    rows = _insert_queue_rows(
        db_cdr,
        instance_id,
        queue_name,
        cat_metric=cat_metric,
        option_pairs=option_pairs,
        members=members,
    )
    db_cdr.commit()
    return _rows_to_queue_response(queue_name, rows)


def delete_queue(
    db_cdr: Session,
    instance_id: int,
    queue_name: str,
    *,
    author: str = "api",
) -> bool:
    if not queue_exists(db_cdr, instance_id, queue_name):
        return False

    _snapshot_queues_before_change(
        db_cdr,
        instance_id,
        f"before delete queue '{queue_name}'",
        author,
    )

    _queue_rows_filter(db_cdr, instance_id, queue_name).delete(
        synchronize_session=False
    )
    db_cdr.commit()
    return True
