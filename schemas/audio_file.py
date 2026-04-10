from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from datetime import date

class AudioFileSchema(BaseModel):
    id:int
    name:str
    format:str
    size_kb:float
    duration_sec:int
    create_date:date
    model_config = ConfigDict(from_attributes=True)