from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from database import get_cdr_db, get_db
from models.asterisk_instance import AsteriskInstance
from schemas.voicemail import DEFAULT_VM_CONTEXT, VoicemailCreate, VoicemailResponse, VoicemailUpdate
from schemas.audio_file import AudioFileSchema
from services import voicemail_config
from services.voicemail_messages import list_voicemail_recordings

router = APIRouter(prefix="/instances/{instance_id}/voicemail")


def _get_instance_or_404(db: Session, instance_id: int) -> AsteriskInstance:
    instance = (
        db.query(AsteriskInstance).filter(AsteriskInstance.id == instance_id).first()
    )
    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    return instance


@router.get("/recordings", response_model=list[AudioFileSchema])
async def list_voicemail_recordings_route(
    instance_id: int = Path(...),
    mailbox: str | None = None,
    db: Session = Depends(get_db),
):
    """Голосовые сообщения на диске (для фронта / раздела аудио)."""
    instance = _get_instance_or_404(db, instance_id)
    return [
        AudioFileSchema(**row)
        for row in list_voicemail_recordings(
            instance, instance_id=instance_id, mailbox=mailbox
        )
    ]


@router.get("/", response_model=list[VoicemailResponse])
async def list_voicemail_boxes(
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    return voicemail_config.list_voicemail_boxes(cdr_db, instance_id)


@router.get("/{mailbox}", response_model=VoicemailResponse)
async def get_voicemail_box(
    mailbox: str = Path(...),
    instance_id: int = Path(...),
    context: str = DEFAULT_VM_CONTEXT,
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    box = voicemail_config.get_voicemail_box(cdr_db, instance_id, mailbox, context)
    if not box:
        raise HTTPException(
            status_code=404, detail=f"Voicemail box '{mailbox}@{context}' not found"
        )
    return box


@router.post("/", response_model=VoicemailResponse, status_code=status.HTTP_201_CREATED)
async def create_voicemail_box(
    data: VoicemailCreate,
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    instance = _get_instance_or_404(db, instance_id)
    try:
        return voicemail_config.create_voicemail_box(
            cdr_db,
            instance_id,
            instance.name,
            data,
            instance=instance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/{mailbox}", response_model=VoicemailResponse)
async def update_voicemail_box(
    data: VoicemailUpdate,
    mailbox: str = Path(...),
    instance_id: int = Path(...),
    context: str = DEFAULT_VM_CONTEXT,
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    if not data.model_dump(exclude_unset=True):
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        return voicemail_config.update_voicemail_box(
            cdr_db, instance_id, mailbox, data, context
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{mailbox}", status_code=status.HTTP_200_OK)
async def delete_voicemail_box(
    mailbox: str = Path(...),
    instance_id: int = Path(...),
    context: str = DEFAULT_VM_CONTEXT,
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    instance = _get_instance_or_404(db, instance_id)
    try:
        deleted = voicemail_config.delete_voicemail_box(
            cdr_db,
            instance_id,
            instance.name,
            mailbox,
            context,
        )
    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e

    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Voicemail box '{mailbox}@{context}' not found"
        )
    return {"message": "success", "mailbox": mailbox, "context": context}
