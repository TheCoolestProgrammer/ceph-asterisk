import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db, get_cdr_db
from models.asterisk_instance import AsteriskInstance
from models.ast_conf import AsteriskConf
from schemas.asterisk import ConfigUpdate
from utils.ast_config_ini import (
    STATIC_REALTIME_CONF_FILES,
    replace_config_from_ini,
    rows_to_ini_content,
)
from utils.instance_paths import writable_config_dir

router = APIRouter(prefix="/instances/{instance_id}/config")


def _config_filename(config_type: str) -> str:
    return config_type if config_type.endswith(".conf") else f"{config_type}.conf"


def _is_db_config(filename: str) -> bool:
    return filename in STATIC_REALTIME_CONF_FILES


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
        try:
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
