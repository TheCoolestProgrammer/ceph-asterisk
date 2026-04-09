from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from database import get_db, get_cdr_db
from models.asterisk_instance import AsteriskInstance, CallerIdModes
from models.sip_user import PjsipEndpoint, Choise, PjsipAor
from schemas.asterisk import ConfigUpdate

router = APIRouter(prefix="/instances/{instance_id}/config")


# @router.post("/change_inbound_status")
# async def change_inbound_status(choise:CallerIdModes, instance_id:int=Path(...),db:Session=Depends(get_db) ,cdr_db: Session = Depends(get_cdr_db)):
#     instance = db.get(AsteriskInstance, instance_id)
#     if not instance:
#         raise HTTPException(status_code=404, detail="Instance not found")
#     instance.inbound_mode = choise

#     new_value = Choise.YES if choise == CallerIdModes.ON else Choise.NO
#     new_value_rev = Choise.NO if choise == CallerIdModes.ON else Choise.YES

#     subquery = cdr_db.query(PjsipEndpoint.id).join(PjsipEndpoint.aors_fk).filter(
#         PjsipAor.reg_server == instance.name
#     ).subquery()

#     cdr_db.query(PjsipEndpoint).filter(PjsipEndpoint.id.in_(subquery)).update(
#     {
#         PjsipEndpoint.trust_id_inbound: new_value,
#         PjsipEndpoint.trust_id_outbound: new_value_rev
#     },
#     synchronize_session=False
# )
    # db.query(PjsipEndpoint).filter(PjsipEndpoint.aors_fk.res_server==instance.name).update({PjsipEndpoint.trust_id_inbound: new_value})
    # db.query(PjsipEndpoint).update({PjsipEndpoint.trust_id_outbound: new_value_rev})
    # db.commit()
    # cdr_db.commit()

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
