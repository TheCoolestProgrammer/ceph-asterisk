from sqlalchemy import Column, Integer, String
from app.core.database import BaseCDR
from sqlalchemy.orm import Mapped, mapped_column


class AsteriskConf(BaseCDR):
    __tablename__ = "ast_config"

    id = Column(Integer, primary_key=True, index=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cat_metric: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Приоритет секции [section] (чем меньше, тем выше)
    var_metric: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Приоритет опции внутри секции (чем меньше, тем выше)
    filename: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # Имя файла (например, 'queues.conf')
    category: Mapped[str] = mapped_column(
        String(128), nullable=False, default="general"
    )  # Секция в файле, например 'general' или 'myqueue'
    var_name: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # Название опции (например, 'context')
    var_val: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # Значение опции (например, 'from-internal')
    commented: Mapped[int] = mapped_column(
        Integer, default=0
    )  # Закомментирована ли опция (0 - нет, 1 - да)
