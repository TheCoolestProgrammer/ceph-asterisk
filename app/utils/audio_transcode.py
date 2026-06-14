"""Перекодировка аудио через SoX (легче FFmpeg по ресурсам)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from loguru import logger

ASTERISK_SAMPLE_RATE = 8000
PREVIEW_SAMPLE_RATE = 44100
MONO_CHANNELS = 1
PCM_BITS = 16

# SoX не всегда определяет telephony-расширения по имени файла.
SOX_INPUT_TYPES: dict[str, str | None] = {
    "wav": None,
    "mp3": None,
    "gsm": "gsm",
    "ulaw": "ul",
    "alaw": "al",
}


def _input_type_for_path(path: Path) -> str | None:
    return SOX_INPUT_TYPES.get(path.suffix.lstrip(".").lower())


def _run_sox(
    input_path: Path,
    *,
    sample_rate: int,
    output_path: Path | None = None,
    output_stdout: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    cmd = ["sox"]
    input_type = _input_type_for_path(input_path)
    if input_type:
        cmd.extend(["-t", input_type])
    cmd.append(str(input_path))
    cmd.extend(
        [
            "-r",
            str(sample_rate),
            "-c",
            str(MONO_CHANNELS),
            "-b",
            str(PCM_BITS),
        ]
    )
    if output_stdout:
        cmd.extend(["-t", "wav", "-"])
    elif output_path is not None:
        cmd.append(str(output_path))
    else:
        raise ValueError("Укажите output_path или output_stdout=True")

    return subprocess.run(
        cmd,
        capture_output=True,
        check=False,
    )


def convert_to_asterisk_wav(input_path: str | Path, output_path: str | Path) -> bool:
    """Конвертирует файл в WAV 8 kHz mono 16-bit для Asterisk."""
    source = Path(input_path)
    target = Path(output_path)
    result = _run_sox(
        source,
        sample_rate=ASTERISK_SAMPLE_RATE,
        output_path=target,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        logger.error(f"SoX conversion error for {source}: {stderr}")
        return False
    return True


def transcode_for_preview(source: Path) -> tuple[bytes, str]:
    """Конвертирует звук в WAV 44.1 kHz для браузера."""
    result = _run_sox(
        source,
        sample_rate=PREVIEW_SAMPLE_RATE,
        output_stdout=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"SoX preview transcode failed for {source}: {stderr}")
    return result.stdout, f"{source.stem}.wav"
