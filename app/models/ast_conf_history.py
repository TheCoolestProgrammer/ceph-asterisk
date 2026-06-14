import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import BaseCDR


class AsteriskConfigHistory(BaseCDR):
    """Неизменяемые снимки конфигурационных файлов (холодное хранилище)."""

    __tablename__ = "ast_config_history"
    __table_args__ = (
        UniqueConstraint(
            "instance_id",
            "filename",
            "version",
            name="uq_ast_config_history_instance_file_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    author: Mapped[str] = mapped_column(String(128), nullable=False)
