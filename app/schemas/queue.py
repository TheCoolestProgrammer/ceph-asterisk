import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

QUEUE_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")
RESERVED_QUEUE_NAMES = frozenset({"general"})

KNOWN_QUEUE_OPTION_FIELDS = frozenset(
    {"strategy", "timeout", "retry", "musicclass", "ringinuse", "maxlen"}
)


def validate_queue_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("queue name must not be empty")
    if name.lower() in RESERVED_QUEUE_NAMES:
        raise ValueError(f"queue name '{name}' is reserved")
    if not QUEUE_NAME_PATTERN.match(name):
        raise ValueError(
            "queue name must start with a letter and contain only letters, digits, _ or -"
        )
    return name


class QueueCreate(BaseModel):
    name: str
    strategy: str = "rrmemory"
    timeout: int = Field(default=20, ge=1)
    retry: int = Field(default=5, ge=0)
    musicclass: str = "default"
    ringinuse: Optional[str] = None
    maxlen: Optional[int] = Field(default=None, ge=0)
    members: list[str] = Field(default_factory=list)
    options: dict[str, str] = Field(default_factory=dict)
    change_author: Optional[str] = "api"

    @field_validator("name")
    @classmethod
    def queue_name(cls, value: str) -> str:
        return validate_queue_name(value)

    @field_validator("members")
    @classmethod
    def members_not_empty(cls, value: list[str]) -> list[str]:
        return [member.strip() for member in value if member.strip()]


class QueueUpdate(BaseModel):
    strategy: Optional[str] = None
    timeout: Optional[int] = Field(default=None, ge=1)
    retry: Optional[int] = Field(default=None, ge=0)
    musicclass: Optional[str] = None
    ringinuse: Optional[str] = None
    maxlen: Optional[int] = Field(default=None, ge=0)
    members: Optional[list[str]] = None
    options: Optional[dict[str, str]] = None
    change_author: Optional[str] = "api"

    @field_validator("members")
    @classmethod
    def members_strip(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        return [member.strip() for member in value if member.strip()]


class QueueResponse(BaseModel):
    name: str
    strategy: Optional[str] = None
    timeout: Optional[str] = None
    retry: Optional[str] = None
    musicclass: Optional[str] = None
    ringinuse: Optional[str] = None
    maxlen: Optional[str] = None
    members: list[str] = Field(default_factory=list)
    options: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)
