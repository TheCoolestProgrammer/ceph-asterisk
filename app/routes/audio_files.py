import os
import shutil

from fastapi import APIRouter, Depends, HTTPException, File, Path, Query, UploadFile
from fastapi.responses import Response
from app.core.config import config
from app.core.database import get_db
from app.models.asterisk_instance import AsteriskInstance
from app.models.audio_files import AudioFile, AudioFormat
from starlette.concurrency import run_in_threadpool
import wave

from app.schemas.audio_file import AudioFileSchema
from app.utils.audio_library import (
    resolve_shared_sound_path,
    sync_disk_library_to_db,
)
from app.utils.audio_transcode import convert_to_asterisk_wav, transcode_for_preview
from app.utils.instance_volumes import shared_sounds_writable_dir
from app.services.voicemail_messages import (
    list_voicemail_recordings,
    parse_voicemail_entry_id,
    resolve_voicemail_audio_path,
)
from sqlalchemy.orm import Session


router = APIRouter(prefix="/audio_files")


def _library_items(db: Session) -> list[AudioFileSchema]:
    rows = db.query(AudioFile).all()
    return [
        AudioFileSchema(
            id=row.id,
            name=row.name,
            format=row.format,
            size_kb=row.size_kb,
            duration_sec=row.duration_sec,
            create_date=row.create_date,
            source="library",
        )
        for row in rows
    ]


@router.post("/upload_audio")
async def upload_audio(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename_parts = file.filename.rsplit(".", 1)
    if len(filename_parts) < 2:
        raise HTTPException(status_code=400, detail="Файл без расширения")

    name_without_ext, file_ext = filename_parts
    file_ext = file_ext.lower()

    if file_ext not in [f.value for f in AudioFormat]:
        raise HTTPException(status_code=400, detail=f"Формат .{file_ext} не поддерживается")

    sounds_dir = shared_sounds_writable_dir()

    input_path = os.path.join(sounds_dir, file.filename)
    output_path = os.path.join(sounds_dir, f"{name_without_ext}.wav")

    try:
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при записи на диск: {e}")

    success = await run_in_threadpool(convert_to_asterisk_wav, input_path, output_path)

    if not success:
        if os.path.exists(input_path):
            os.remove(input_path)
        raise HTTPException(status_code=500, detail="Ошибка конвертации аудио")

    try:
        os.chown(output_path, config.ASTERISK_UID, config.ASTERISK_GID)
        if input_path != output_path:
            os.remove(input_path)
    except (AttributeError, PermissionError):
        pass

    duration = 0
    with wave.open(output_path, "rb") as f:
        frames = f.getnframes()
        rate = f.getframerate()
        duration = frames / float(rate)

    af = AudioFile(
        name=f"{name_without_ext}",
        format="wav",
        size_kb=os.path.getsize(output_path) / 1024,
        duration_sec=duration,
    )
    db.add(af)
    db.commit()
    return {"filename": f"{name_without_ext}.wav", "status": "converted"}


@router.get("/get_files", response_model=list[AudioFileSchema])
async def get_audio(
    instance_id: int | None = Query(None, description="Инстанс АТС для записей voicemail"),
    include_voicemail: bool = Query(
        False, description="Добавить голосовые сообщения с диска инстанса"
    ),
    mailbox: str | None = Query(None, description="Фильтр по ящику, напр. 101"),
    db: Session = Depends(get_db),
):
    sync_disk_library_to_db(db)
    items = _library_items(db)
    if include_voicemail:
        if instance_id is None:
            raise HTTPException(
                status_code=400,
                detail="Укажите instance_id при include_voicemail=true",
            )
        instance = (
            db.query(AsteriskInstance)
            .filter(AsteriskInstance.id == instance_id)
            .first()
        )
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        items.extend(
            AudioFileSchema(**row)
            for row in list_voicemail_recordings(
                instance, instance_id=instance_id, mailbox=mailbox
            )
        )
    return items


@router.get("/get_file/{file_id}")
async def get_audio_file(
    file_id: str = Path(..., description="id из БД или vm:{instance_id}:{path}"),
    db: Session = Depends(get_db),
):
    parsed = parse_voicemail_entry_id(file_id)
    if parsed is not None:
        inst_id, rel_path = parsed
        instance = (
            db.query(AsteriskInstance).filter(AsteriskInstance.id == inst_id).first()
        )
        if not instance:
            raise HTTPException(status_code=404, detail="Instance not found")
        try:
            audio_path = resolve_voicemail_audio_path(instance, rel_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Запись не найдена") from None
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        preview_bytes, preview_name = await run_in_threadpool(
            transcode_for_preview, audio_path
        )
        return Response(
            content=preview_bytes,
            media_type="audio/wav",
            headers={"Content-Disposition": f'inline; filename="{preview_name}"'},
        )

    try:
        numeric_id = int(file_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Некорректный id файла")

    audio = db.query(AudioFile).filter(AudioFile.id == numeric_id).first()

    if not audio:
        raise HTTPException(status_code=404, detail="Файл не найден в базе данных")

    file_path = resolve_shared_sound_path(audio.name, audio.format)
    if file_path is None:
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")

    preview_bytes, preview_name = await run_in_threadpool(
        transcode_for_preview, file_path
    )
    return Response(
        content=preview_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": f'inline; filename="{preview_name}"'},
    )


@router.delete("/delete_file/{file_id}")
async def delete_audio(file_id: int = Path(...), db: Session = Depends(get_db)):
    audio = db.query(AudioFile).filter(AudioFile.id == file_id).first()
    if not audio:
        raise HTTPException(status_code=404, detail="Файл не найден")

    sound_path = resolve_shared_sound_path(audio.name, audio.format)
    if sound_path is not None:
        os.remove(sound_path)

    db.delete(audio)
    db.commit()

    return audio
