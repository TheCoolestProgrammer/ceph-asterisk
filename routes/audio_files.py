import os
import shutil

from fastapi import APIRouter, UploadFile, Depends, HTTPException, File, Path
from fastapi.responses import FileResponse
from config import config
from loguru import logger
from database import SessionLocal, get_db
from models.asterisk_instance import AsteriskInstance
from models.audio_files import AudioFile, AudioFormat
from pydub import AudioSegment
from starlette.concurrency import run_in_threadpool
import wave

from schemas.audio_file import (
    AudioFileSchema
)
from sqlalchemy.orm import Session


router = APIRouter(prefix="/audio_files")


# Вынесем конвертацию в отдельную функцию, чтобы запускать её в потоке
def convert_to_asterisk_wav(input_path: str, output_path: str):
    try:
        # Pydub сам поймет формат (mp3, wav и т.д.), если установлен ffmpeg
        audio = AudioSegment.from_file(input_path)
        audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)
        audio.export(output_path, format="wav")
        return True
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        return False

@router.post("/upload_audio")
async def upload_audio(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Безопасное извлечение расширения
    filename_parts = file.filename.rsplit(".", 1)
    if len(filename_parts) < 2:
        raise HTTPException(status_code=400, detail="Файл без расширения")
    
    name_without_ext, file_ext = filename_parts
    file_ext = file_ext.lower()

    if file_ext not in [f.value for f in AudioFormat]:
        raise HTTPException(status_code=400, detail=f"Формат .{file_ext} не поддерживается")

    # 2. Пути
    sounds_dir = f"/app/{config.CONFIG_FOLDER}/sounds"
    os.makedirs(sounds_dir, exist_ok=True)
    
    input_path = os.path.join(sounds_dir, file.filename)
    output_path = os.path.join(sounds_dir, f"{name_without_ext}.wav")

    # 3. Сохранение файла (асинхронно читаем, синхронно пишем)
    try:
        with open(input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при записи на диск: {e}")

    # 4. Конвертация (выполняем в отдельном потоке, чтобы не блокировать Event Loop)
    success = await run_in_threadpool(convert_to_asterisk_wav, input_path, output_path)
    
    if not success:
        if os.path.exists(input_path): os.remove(input_path) # Чистим мусор
        raise HTTPException(status_code=500, detail="Ошибка конвертации аудио")

    # 5. Права доступа (если запуск под root)
    try:
        os.chown(output_path, config.ASTERISK_UID, config.ASTERISK_GID)
        # Если оригинальный файл (mp3) больше не нужен - удаляем
        if input_path != output_path:
            os.remove(input_path)
    except AttributeError: # На Windows chown нет
        pass
    except PermissionError:
        logger.warning("Недостаточно прав для chown. Проверьте пользователя контейнера.")
    
    duration = 0
    with wave.open(output_path, 'rb') as f:
        frames = f.getnframes()
        rate = f.getframerate()
        duration = frames / float(rate)
    
    af = AudioFile(
        name = f"{name_without_ext}",
        format= "wav",
        size_kb= os.path.getsize(output_path) / 1024,
        duration_sec=duration
    )
    db.add(af)
    db.commit()
    return {"filename": f"{name_without_ext}.wav", "status": "converted"}


@router.get("/get_files", response_model=list[AudioFileSchema])
async def get_audio(db: Session = Depends(get_db)):
    audio = db.query(AudioFile).all()
    return audio


@router.get("/get_file/{id}")
async def get_audio_file(id: int, db: Session = Depends(get_db)):
    # 1. Ищем запись в базе
    sounds_dir = f"/app/{config.CONFIG_FOLDER}/sounds"

    audio = db.query(AudioFile).filter(AudioFile.id == id).first()
    
    if not audio:
        raise HTTPException(status_code=404, detail="Файл не найден в базе данных")

    # 2. Формируем путь к файлу (например, name + format)
    file_path = os.path.join(sounds_dir, f"{audio.name}.{audio.format}")

    # 3. Проверяем, существует ли физический файл
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Файл не найден на сервере")

    # 4. Возвращаем файл. 
    # media_type поможет браузеру понять, что это аудио
    return FileResponse(
        path=file_path, 
        media_type=f"audio/{audio.format}",
        filename=f"{audio.name}.{audio.format}"
    )

@router.delete("/delete_file/{file_id}")
async def delete_audio(file_id:int=Path(...), db: Session = Depends(get_db)):
    audio = db.query(AudioFile).filter(AudioFile.id==file_id).first()
    
    sound_dir = f"/app/{config.CONFIG_FOLDER}/sounds/{audio.name}.{audio.format}"

    os.remove(sound_dir)
    
    db.delete(audio)
    db.commit()

    return audio