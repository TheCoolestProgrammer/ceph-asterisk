from pydantic import BaseModel, ConfigDict
from typing import Optional


class DialplanRowResponse(BaseModel):
    """Строка диалплана (соответствует ast_config)"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    cat_metric: int
    var_metric: int
    category: str
    var_name: str
    var_val: str
    commented: int


class DialplanResponse(BaseModel):
    """Полный диалплан для context'а"""

    instance_id: int
    filename: str
    rows: list[DialplanRowResponse]


class DialplanRowUpdate(BaseModel):
    """Строка диалплана для обновления"""

    cat_metric: int
    var_metric: int
    category: str
    var_name: str
    var_val: str
    commented: int = 0


class DialplanUpdate(BaseModel):
    """Обновление диалплана (роут для сохранения)"""

    filename: str  # extensions.conf
    rows: list[DialplanRowUpdate]
    change_author: Optional[str] = "api"
    description: Optional[str] = None
    reload_asterisk: bool = False  # Перезагрузить Asterisk после сохранения


class DialplanContextUpdate(BaseModel):
    """Обновление диалплана для одного контекста"""

    filename: str  # extensions.conf
    rows: list[DialplanRowUpdate]
    change_author: Optional[str] = "api"
    description: Optional[str] = None
    reload_asterisk: bool = False  # Перезагрузить Asterisk после сохранения
