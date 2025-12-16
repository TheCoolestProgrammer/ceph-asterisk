from datetime import datetime
import random
import subprocess
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


from database import get_db
from models.asterisk_instance import AsteriskInstance

router = APIRouter(prefix="/instances")


@router.post("{instance_id}/reload")
async def reload_instance(instance_id: int, db: Session = Depends(get_db)):
    """Перезагрузка конфигурации Asterisk"""
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        # Execute reload command in container
        result = subprocess.run(
            [
                "docker",
                "exec",
                f"asterisk-{instance.name}",
                "asterisk",
                "-rx",
                "reload",
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return {"message": "Configuration reloaded successfully"}
        else:
            raise HTTPException(
                status_code=500, detail=f"Failed to reload: {result.stderr}"
            )

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error reloading configuration: {str(e)}"
        )


@router.post("{instance_id}/simulate-call")
async def simulate_single_call(
    instance_id: int,
    src: str = "6001",
    dst: str = "6002",
    db: Session = Depends(get_db),
):
    """Симуляция одного тестового звонка"""

    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")

    try:
        # Используем Asterisk Manager Interface для инициации звонка
        # Или создаем CDR запись напрямую
        call_date = datetime.now()

        query = """
        INSERT INTO cdr 
        (calldate, clid, src, dst, dcontext, channel, dstchannel, lastapp, lastdata, 
         duration, billsec, disposition, amaflags, accountcode, uniqueid, userfield, instance_name)
        VALUES 
        (:calldate, :clid, :src, :dst, :dcontext, :channel, :dstchannel, :lastapp, :lastdata,
         :duration, :billsec, :disposition, :amaflags, :accountcode, :uniqueid, :userfield, :instance_name)
        """

        params = {
            "calldate": call_date,
            "clid": f'"{src}" <{src}>',
            "src": src,
            "dst": dst,
            "dcontext": "local",
            "channel": f"SIP/{src}-00000001",
            "dstchannel": f"SIP/{dst}-00000002",
            "lastapp": "Dial",
            "lastdata": f"SIP/{dst},20",
            "duration": 30,
            "billsec": 25,
            "disposition": "ANSWERED",
            "amaflags": 0,
            "accountcode": "",
            "uniqueid": f"{int(call_date.timestamp())}.{random.randint(1000, 9999)}",
            "userfield": "manual_simulation",
            "instance_name": instance.name,
        }

        db.execute(text(query), params)
        db.commit()

        return {"message": f"Call simulated from {src} to {dst}", "call_data": params}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to simulate call: {str(e)}"
        )
