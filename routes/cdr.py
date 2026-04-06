from datetime import datetime, timedelta
import random
from typing import Optional
from fastapi import APIRouter, Depends, status
from sqlalchemy import text

from database import get_db, get_cdr_db
from schemas.asterisk import ActiveCall, CDRGet, CDRRecord
from sqlalchemy.orm import Session
from models.cdr import CDR
from schemas.cdr import CDRRecord, CDRInputData

router = APIRouter(prefix="/cdr")


@router.get("/", response_model=list[CDRRecord])
async def get_cdr_history(
    data:CDRInputData = Depends(),
    db: Session = Depends(get_cdr_db),
):
    query = db.query(CDR)
    if data.instance_name:
        query = query.filter(CDR.uniqueid.like(f"%{data.instance_name}%"))
    
    if data.src:
        query = query.filter(CDR.src.like(f"%{data.src}%"))
    
    if data.dst:
        query = query.filter(CDR.dst.like(f"%{data.dst}%"))
        
    if data.date_from:
        query = query.filter(CDR.start >= data.date_from)
        
    if data.date_to:
        query = query.filter(CDR.end <= data.date_to)

    return query.order_by(CDR.start.desc())\
                .limit(data.limit)\
                .offset(data.offset)\
                .all()



def row_to_dict(row):
    """Преобразование SQLAlchemy Row в словарь"""
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    elif hasattr(row, "_asdict"):
        return row._asdict()
    else:
        return dict(row)


@router.get("/active/"
            # response_model=list[ActiveCall]
            )
async def get_active_calls(
    instance_name: Optional[str] = None, db: Session = Depends(get_db)
):
    #TODO: переписать роут так, чтобы он обращался к ARI/AMI

    return status.HTTP_404_NOT_FOUND

    # """Получение списка активных звонков"""
    # query = "SELECT * FROM active_calls WHERE 1=1"
    # params = {}

    # if instance_name:
    #     query += " AND instance_name = :instance_name"
    #     params["instance_name"] = instance_name

    # result = db.execute(text(query), params)
    # calls = result.fetchall()

    # return [row_to_dict(call) for call in calls]


@router.get("/stats/")
async def get_call_stats(
    instance_name: str,
    period: str = "day",  # day, week, month
    db: Session = Depends(get_cdr_db),
):
    """Получение статистики звонков"""

    if period == "day":
        interval = 1
    elif period == "week":
        interval = 7
    else:
        interval = 30

    query = (
        """
    SELECT 
        COUNT(*) as total_calls,
        SUM(duration) as total_duration,
        AVG(duration) as avg_duration,
        SUM(billsec) as total_billsec,
        AVG(billsec) as avg_billsec,
        disposition,
        COUNT(CASE WHEN disposition = 'ANSWERED' THEN 1 END) as answered_calls,
        COUNT(CASE WHEN disposition = 'NO ANSWER' THEN 1 END) as no_answer_calls,
        COUNT(CASE WHEN disposition = 'BUSY' THEN 1 END) as busy_calls,
        COUNT(CASE WHEN disposition = 'FAILED' THEN 1 END) as failed_calls
    FROM asterisk_cdr 
    WHERE uniqueid like :instance_name 
    AND start >= DATE_SUB(NOW(), INTERVAL :interval DAY)
    GROUP BY disposition
    """
    )
    params = {
        "instance_name":f"%{instance_name}%",
        "interval":interval
    }
    result = db.execute(text(query), params)
    stats = result.fetchall()

    return {
        "period": period,
        "instance_name": instance_name,
        "stats": [row_to_dict(stat) for stat in stats],
    }


@router.post("/simulate/")
async def simulate_calls(
    instance_name: str, count: int = 5, db: Session = Depends(get_db)
):
    #TODO: переписать!

    return status.HTTP_404_NOT_FOUND
    # """Симуляция тестовых звонков"""

    # extensions = ["6001", "6002", "6003", "6004", "6005"]
    # dispositions = ["ANSWERED", "NO ANSWER", "BUSY", "FAILED"]

    # simulated_calls = []

    # for i in range(count):
    #     # Генерируем случайные данные звонка
    #     call_date = datetime.now() - timedelta(hours=random.randint(0, 24 * 7))
    #     src = random.choice(extensions)
    #     dst = random.choice([e for e in extensions if e != src])
    #     duration = random.randint(0, 300)
    #     billsec = random.randint(0, duration)
    #     disposition = random.choice(dispositions)

    #     # Вставляем тестовый CDR
    #     query = """
    #     INSERT INTO cdr 
    #     (calldate, clid, src, dst, dcontext, channel, dstchannel, lastapp, lastdata, 
    #      duration, billsec, disposition, amaflags, accountcode, uniqueid, userfield, instance_name)
    #     VALUES 
    #     (:calldate, :clid, :src, :dst, :dcontext, :channel, :dstchannel, :lastapp, :lastdata,
    #      :duration, :billsec, :disposition, :amaflags, :accountcode, :uniqueid, :userfield, :instance_name)
    #     """

    #     params = {
    #         "calldate": call_date,
    #         "clid": f'"{random.choice(["John", "Jane", "Mike", "Sarah"])}" <{src}>',
    #         "src": src,
    #         "dst": dst,
    #         "dcontext": "local",
    #         "channel": f"SIP/{src}-0000000{random.randint(1, 9)}",
    #         "dstchannel": f"SIP/{dst}-0000000{random.randint(1, 9)}",
    #         "lastapp": "Dial",
    #         "lastdata": f"SIP/{dst},20",
    #         "duration": duration,
    #         "billsec": billsec,
    #         "disposition": disposition,
    #         "amaflags": 0,
    #         "accountcode": "",
    #         "uniqueid": f"{int(call_date.timestamp())}.{random.randint(1000, 9999)}",
    #         "userfield": "simulated_call",
    #         "instance_name": instance_name,
    #     }

    #     db.execute(text(query), params)
    #     simulated_calls.append(params)

    # db.commit()

    # return {
    #     "message": f"Simulated {count} calls for {instance_name}",
    #     "simulated_calls": simulated_calls,
    # }
