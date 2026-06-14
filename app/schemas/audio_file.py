from datetime import date
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict


class AudioFileSchema(BaseModel):
    id: Union[int, str]
    name: str
    format: str
    size_kb: float
    duration_sec: int
    create_date: date
    source: Literal["library", "voicemail"] = "library"
    instance_id: Optional[int] = None
    instance_name: Optional[str] = None
    mailbox: Optional[str] = None
    folder: Optional[str] = None
    caller_id: Optional[str] = None
    vm_path: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
