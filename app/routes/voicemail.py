from fastapi import APIRouter, Depends, HTTPException, Path, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_cdr_db, get_db
from app.models.asterisk_instance import AsteriskInstance
from app.schemas.voicemail import (
    DEFAULT_VM_CONTEXT,
    VoicemailCreate,
    VoicemailResponse,
    VoicemailUpdate,
    VoicemailUserBindingRequest,
    VoicemailUserBindingResponse,
    VoicemailUserUnbindRequest,
    VoicemailUserUnbindResponse,
)
from app.schemas.audio_file import AudioFileSchema
from app.services import voicemail_config
from app.services.voicemail_messages import (
    list_voicemail_recordings,
    resolve_voicemail_audio_path,
    resolve_voicemail_message_file,
)

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


@router.get("/{mailbox}/recordings", response_model=list[AudioFileSchema])
async def list_voicemail_recordings_by_mailbox_route(
    mailbox: str = Path(...),
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
):
    """Голосовые сообщения конкретного ящика."""
    instance = _get_instance_or_404(db, instance_id)
    return [
        AudioFileSchema(**row)
        for row in list_voicemail_recordings(
            instance, instance_id=instance_id, mailbox=mailbox
        )
    ]


@router.get("/{mailbox}/recordings/file/{filename}")
async def get_voicemail_recording_file_route(
    mailbox: str = Path(...),
    filename: str = Path(..., description="Имя файла, например msg0000.wav"),
    instance_id: int = Path(...),
    folder: str = "INBOX",
    context: str = DEFAULT_VM_CONTEXT,
    db: Session = Depends(get_db),
):
    """Отдаёт конкретный аудиофайл voicemail по ящику."""
    instance = _get_instance_or_404(db, instance_id)
    try:
        audio_path = resolve_voicemail_message_file(
            instance,
            context=context,
            mailbox=mailbox,
            folder=folder,
            filename=filename,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Запись не найдена") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    suffix = audio_path.suffix.lower()
    media_by_suffix = {
        ".wav": "audio/wav",
        ".gsm": "audio/gsm",
        ".ulaw": "audio/basic",
        ".alaw": "audio/basic",
        ".sln": "audio/basic",
        ".sln16": "audio/basic",
    }
    media = media_by_suffix.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(audio_path),
        media_type=media,
        filename=audio_path.name,
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/", response_model=list[VoicemailResponse])
async def list_voicemail_boxes(
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    _get_instance_or_404(db, instance_id)
    return voicemail_config.list_voicemail_boxes(cdr_db, instance_id)


@router.get("/by-user/{user_id}", response_model=VoicemailResponse)
async def get_voicemail_box_by_user_id(
    user_id: str = Path(...),
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    instance = _get_instance_or_404(db, instance_id)
    box = voicemail_config.get_voicemail_box_by_user_id(
        cdr_db, instance_id, instance.name, user_id
    )
    if not box:
        raise HTTPException(
            status_code=404, detail=f"Voicemail box for user '{user_id}' not found"
        )
    return box


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


@router.post("/bind-user", response_model=VoicemailUserBindingResponse)
async def bind_user_to_voicemail_box(
    data: VoicemailUserBindingRequest,
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    instance = _get_instance_or_404(db, instance_id)
    try:
        user_id, mailbox, context = voicemail_config.bind_user_to_voicemail_box(
            cdr_db,
            instance_id,
            instance.name,
            user_id=data.user_id,
            mailbox=data.mailbox,
            context=data.context,
        )
        return VoicemailUserBindingResponse(
            user_id=user_id,
            mailbox=mailbox,
            context=context,
            linked=True,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/unbind-user", response_model=VoicemailUserUnbindResponse)
async def unbind_user_from_voicemail_box(
    data: VoicemailUserUnbindRequest,
    instance_id: int = Path(...),
    db: Session = Depends(get_db),
    cdr_db: Session = Depends(get_cdr_db),
):
    instance = _get_instance_or_404(db, instance_id)
    try:
        user_id, mailbox, context = voicemail_config.unbind_user_from_voicemail_box(
            cdr_db,
            instance.name,
            user_id=data.user_id,
            mailbox=data.mailbox,
            context=data.context,
        )
        return VoicemailUserUnbindResponse(
            user_id=user_id,
            mailbox=mailbox,
            context=context,
            unlinked=True,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        cdr_db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e


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
            db=db,
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
