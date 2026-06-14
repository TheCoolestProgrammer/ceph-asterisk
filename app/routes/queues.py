from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_cdr_db, get_db
from app.models.asterisk_instance import AsteriskInstance
from app.schemas.queue import QueueCreate, QueueResponse, QueueUpdate
from app.services import queue_config

router = APIRouter(prefix="/instances/{instance_id}/queues")


def _get_instance_or_404(db: Session, instance_id: int) -> AsteriskInstance:
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return instance


@router.get("/", response_model=list[QueueResponse])
async def list_queues(
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    return queue_config.list_queues(cdr_db, instance_id)


@router.get("/{queue_name}", response_model=QueueResponse)
async def get_queue(
    queue_name: str = Path(...),
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    queue = queue_config.get_queue(cdr_db, instance_id, queue_name)
    if not queue:
        raise HTTPException(status_code=404, detail=f"Queue '{queue_name}' not found")
    return queue


@router.post("/", response_model=QueueResponse, status_code=status.HTTP_201_CREATED)
async def create_queue(
    data: QueueCreate,
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    try:
        return queue_config.create_queue(
            cdr_db, instance_id, data, author=data.change_author or "api"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/{queue_name}", response_model=QueueResponse)
async def update_queue(
    data: QueueUpdate,
    queue_name: str = Path(...),
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    if not data.model_dump(exclude_unset=True, exclude={"change_author"}):
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        return queue_config.update_queue(
            cdr_db,
            instance_id,
            queue_name,
            data,
            author=data.change_author or "api",
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{queue_name}", status_code=status.HTTP_200_OK)
async def delete_queue(
    queue_name: str = Path(...),
    instance_id: int = Path(...),
    change_author: str = Query(default="api"),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    try:
        deleted = queue_config.delete_queue(
            cdr_db, instance_id, queue_name, author=change_author
        )
    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Queue '{queue_name}' not found")
    return {"message": "success", "queue": queue_name}
