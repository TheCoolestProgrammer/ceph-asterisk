import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db, get_cdr_db
from app.models.asterisk_instance import AsteriskInstance
from app.models.ast_conf import AsteriskConf
from app.models.ast_conf_history import AsteriskConfigHistory
from app.schemas.asterisk import (
    ConfigHistoryListResponse,
    ConfigHistoryEntry,
    ConfigHistoryVersionContent,
    ConfigRollbackRequest,
    ConfigRollbackResponse,
    ConfigUpdate,
)
from app.services.ast_config_history import (
    get_file_history,
    get_history_version_content,
    rollback_to_version,
    save_file_version,
)
from app.services.asterisk_reload import AsteriskReloadError, reload_asterisk_config
from app.utils.ast_config_ini import (
    STATIC_REALTIME_CONF_FILES,
    replace_config_from_ini,
    rows_to_ini_content,
)
from app.utils.instance_paths import writable_config_dir

router = APIRouter(prefix="/instances/{instance_id}/config")


def _config_filename(config_type: str) -> str:
    return config_type if config_type.endswith(".conf") else f"{config_type}.conf"


def _is_db_config(filename: str) -> bool:
    return filename in STATIC_REALTIME_CONF_FILES


def _require_db_config(filename: str) -> None:
    if not _is_db_config(filename):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Config '{filename}' is stored on disk; "
                "version history is only available for database realtime configs"
            ),
        )


def _get_instance_or_404(db: Session, instance_id: int) -> AsteriskInstance:
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return instance


def _get_history_entry(
    db_cdr: Session,
    instance_id: int,
    filename: str,
    *,
    history_id: int | None = None,
    version: int | None = None,
) -> AsteriskConfigHistory:
    if history_id is not None and version is not None:
        raise HTTPException(
            status_code=400,
            detail="Specify either history_id or version, not both",
        )
    if history_id is None and version is None:
        raise HTTPException(
            status_code=400,
            detail="Specify history_id or version",
        )

    if history_id is not None:
        entry = db_cdr.get(AsteriskConfigHistory, history_id)
    else:
        entry = (
            db_cdr.query(AsteriskConfigHistory)
            .filter(
                AsteriskConfigHistory.instance_id == instance_id,
                AsteriskConfigHistory.filename == filename,
                AsteriskConfigHistory.version == version,
            )
            .first()
        )

    if entry is None:
        raise HTTPException(status_code=404, detail="History record not found")
    if entry.instance_id != instance_id or entry.filename != filename:
        raise HTTPException(
            status_code=400,
            detail="History record does not match this instance or config file",
        )
    return entry


def _resolve_history_entry(
    db_cdr: Session,
    instance_id: int,
    filename: str,
    body: ConfigRollbackRequest,
) -> AsteriskConfigHistory:
    return _get_history_entry(
        db_cdr,
        instance_id,
        filename,
        history_id=body.history_id,
        version=body.version,
    )


@router.get(
    "/{config_type}/history/{version}",
    response_model=ConfigHistoryVersionContent,
)
async def get_config_history_version(
    instance_id: int,
    config_type: str,
    version: int,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Текст конфигурационного файла для указанной версии из истории."""
    _get_instance_or_404(db, instance_id)
    filename = _config_filename(config_type)
    _require_db_config(filename)

    try:
        entry, content = get_history_version_content(
            db_cdr, instance_id, filename, version
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return ConfigHistoryVersionContent(
        config_type=config_type,
        filename=filename,
        version=entry.version,
        history_id=entry.id,
        description=entry.description,
        created_at=entry.created_at,
        author=entry.author,
        content=content,
    )


@router.get("/{config_type}/history", response_model=ConfigHistoryListResponse)
async def get_config_history(
    instance_id: int,
    config_type: str,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Список версий конфигурационного файла (без тела снапшота)."""
    _get_instance_or_404(db, instance_id)
    filename = _config_filename(config_type)
    _require_db_config(filename)

    entries = get_file_history(db_cdr, instance_id, filename)
    return ConfigHistoryListResponse(
        config_type=config_type,
        filename=filename,
        items=[ConfigHistoryEntry.model_validate(e) for e in entries],
    )


@router.post("/{config_type}/rollback", response_model=ConfigRollbackResponse)
async def rollback_config(
    instance_id: int,
    config_type: str,
    body: ConfigRollbackRequest,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Откат «горячего» ast_config к выбранной версии из истории."""
    instance = _get_instance_or_404(db, instance_id)
    filename = _config_filename(config_type)
    _require_db_config(filename)

    history_entry = _resolve_history_entry(db_cdr, instance_id, filename, body)
    author = body.change_author or "api"

    try:
        snapshot_before = save_file_version(
            db_cdr,
            instance_id,
            filename,
            f"before rollback to version {history_entry.version}",
            author,
            commit=False,
        )
        restored_rows = rollback_to_version(db_cdr, history_entry.id)
    except ValueError as e:
        db_cdr.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        db_cdr.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to rollback config: {e}"
        ) from e

    reload_message = ""
    if body.reload_asterisk:
        try:
            reload_asterisk_config(instance.name)
            reload_message = "; Asterisk reloaded"
        except AsteriskReloadError as e:
            reload_message = f"; Asterisk reload failed: {e.message}"

    return ConfigRollbackResponse(
        message=f"Config {filename} restored to version {history_entry.version}{reload_message}",
        filename=filename,
        restored_version=history_entry.version,
        history_id=history_entry.id,
        rows_restored=len(restored_rows),
        snapshot_saved_version=snapshot_before.version,
    )


@router.put("")
async def update_config(
    instance_id: int,
    config_update: ConfigUpdate,
    db: Session = Depends(get_db),
    db_cdr: Session = Depends(get_cdr_db),
):
    """Обновление конфигурационного файла (БД или диск)."""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    filename = _config_filename(config_update.config_type)

    if _is_db_config(filename):
        author = config_update.change_author or "api"
        try:
            save_file_version(
                db_cdr,
                instance_id,
                filename,
                f"before update via PUT /config ({config_update.config_type})",
                author,
                commit=False,
            )
            replace_config_from_ini(
                db_cdr, instance_id, filename, config_update.content
            )
            db_cdr.commit()
        except Exception as e:
            db_cdr.rollback()
            raise HTTPException(
                status_code=500, detail=f"Failed to update config in DB: {str(e)}"
            )
        return {"message": f"Config {filename} updated successfully (database)"}

    config_file = os.path.join(writable_config_dir(instance), filename)

    try:
        with open(config_file, "w") as f:
            f.write(config_update.content)
        return {"message": f"Config {filename} updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update config: {str(e)}"
        )


@router.get("/{config_type}")
async def get_config(
    instance_id: int, config_type: str, db: Session = Depends(get_db), db_cdr: Session = Depends(get_cdr_db)
):
    """Получение содержимого конфигурационного файла (БД или диск)."""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    filename = _config_filename(config_type)

    if _is_db_config(filename):
        rows = (
            db_cdr.query(AsteriskConf)
            .filter(
                AsteriskConf.instance_id == instance_id,
                AsteriskConf.filename == filename,
            )
            .order_by(AsteriskConf.cat_metric, AsteriskConf.var_metric)
            .all()
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Config not found in database")
        content = rows_to_ini_content(rows)
        return {"config_type": config_type, "content": content, "source": "database"}

    config_file = os.path.join(writable_config_dir(instance), filename)

    try:
        with open(config_file, "r") as f:
            content = f.read()
        return {"config_type": config_type, "content": content, "source": "disk"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Config file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {str(e)}")
