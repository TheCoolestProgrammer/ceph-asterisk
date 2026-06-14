from datetime import datetime
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, Field

class ParsedMessageModel(BaseModel):
    """Модель данных, собранных Filebeat из лога Asterisk"""
    timestamp: Optional[datetime] = None
    level: str
    pid: Optional[str] = None
    file: Optional[str] = None
    message: str

class LogEntry(BaseModel):
    """Модель отдельной записи лога"""
    message: ParsedMessageModel
    pbx_id: Optional[Union[str, int]] = None

class LogsModel(BaseModel):
    """Главная модель выходных данных для response_model"""
    status: str
    data: List[LogEntry]
    total: int = Field(..., description="Общее количество найденных записей")
    relation: Literal["eq", "gte"] = Field(
        ...,
        description="Точность total: eq — точное значение, gte — не меньше total (ограничение Elasticsearch 10000)",
    )
