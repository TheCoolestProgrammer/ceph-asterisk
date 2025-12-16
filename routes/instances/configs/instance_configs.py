from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.asterisk_instance import AsteriskInstance
from schemas.asterisk import ConfigUpdate

router = APIRouter(prefix="/instances/{instance_id}/config")


@router.put("")
async def update_config(
    instance_id: int, config_update: ConfigUpdate, db: Session = Depends(get_db)
):
    """Обновление конфигурационного файла"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    config_file = f"{instance.config_path}/{config_update.config_type}.conf"

    try:
        with open(config_file, "w") as f:
            f.write(config_update.content)
        return {
            "message": f"Config {config_update.config_type}.conf updated successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to update config: {str(e)}"
        )


@router.get("{config_type}")
async def get_config(instance_id: int, config_type: str, db: Session = Depends(get_db)):
    """Получение содержимого конфигурационного файла"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    config_file = f"{instance.config_path}/{config_type}.conf"

    try:
        with open(config_file, "r") as f:
            content = f.read()
        return {"config_type": config_type, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Config file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read config: {str(e)}")
