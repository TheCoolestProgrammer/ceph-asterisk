from datetime import datetime
from typing import List, Optional, Union, Any
from pydantic import BaseModel, Field

class ParsedMessageModel(BaseModel):
    """Модель данных, полученных из parse_asterisk_log"""
    timestamp: Optional[datetime] = None
    level: str
    pid: Optional[str] = None # str, так как в регулярке \d+, но для безопасности данных лучше str или Optional[int]
    source: str
    msg: str

class LogEntry(BaseModel):
    """Модель отдельной записи лога"""
    message: ParsedMessageModel
    pbx_id: Optional[Union[str, int]] = None

class LogsModel(BaseModel):
    """Главная модель выходных данных для response_model"""
    status: str
    data: List[LogEntry]
    total: int = Field(..., description="Общее количество найденных записей")
