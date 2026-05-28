import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAILBOX_PATTERN = re.compile(r"^[0-9A-Za-z*#][0-9A-Za-z*#_-]*$")
DEFAULT_VM_CONTEXT = "default"
RESERVED_VM_CONTEXTS = frozenset({"general", "zonemessages"})


def validate_mailbox(value: str) -> str:
    mailbox = value.strip()
    if not mailbox:
        raise ValueError("mailbox must not be empty")
    if mailbox.lower() in RESERVED_VM_CONTEXTS:
        raise ValueError(f"context '{mailbox}' is reserved")
    if not MAILBOX_PATTERN.match(mailbox):
        raise ValueError(
            "mailbox must start with a digit, letter, * or # and contain only alphanumeric, _ or -"
        )
    return mailbox


def validate_vm_context(value: str) -> str:
    context = value.strip()
    if not context:
        raise ValueError("context must not be empty")
    if context.lower() in RESERVED_VM_CONTEXTS:
        raise ValueError(f"context '{context}' is reserved")
    return context


class VoicemailCreate(BaseModel):
    """Создание голосового ящика для внутреннего номера (extension)."""

    mailbox: str
    password: str = Field(min_length=4, max_length=10)
    full_name: str = Field(min_length=1, max_length=80)
    email: Optional[str] = Field(default=None, max_length=80)
    context: str = DEFAULT_VM_CONTEXT
    link_endpoint_mwi: bool = True

    @field_validator("mailbox")
    @classmethod
    def mailbox_name(cls, value: str) -> str:
        return validate_mailbox(value)

    @field_validator("context")
    @classmethod
    def vm_context(cls, value: str) -> str:
        return validate_vm_context(value)


class VoicemailUpdate(BaseModel):
    password: Optional[str] = Field(default=None, min_length=4, max_length=10)
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    email: Optional[str] = Field(default=None, max_length=80)


class VoicemailResponse(BaseModel):
    mailbox: str
    context: str
    password: str
    full_name: str
    email: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VoicemailUserBindingRequest(BaseModel):
    user_id: str
    mailbox: str
    context: str = DEFAULT_VM_CONTEXT

    @field_validator("user_id")
    @classmethod
    def user_id_name(cls, value: str) -> str:
        return validate_mailbox(value)

    @field_validator("mailbox")
    @classmethod
    def mailbox_name(cls, value: str) -> str:
        return validate_mailbox(value)

    @field_validator("context")
    @classmethod
    def vm_context(cls, value: str) -> str:
        return validate_vm_context(value)


class VoicemailUserBindingResponse(BaseModel):
    user_id: str
    mailbox: str
    context: str
    linked: bool = True


class VoicemailUserUnbindRequest(BaseModel):
    user_id: str
    mailbox: str | None = None
    context: str = DEFAULT_VM_CONTEXT

    @field_validator("user_id")
    @classmethod
    def user_id_name(cls, value: str) -> str:
        return validate_mailbox(value)

    @field_validator("mailbox")
    @classmethod
    def mailbox_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_mailbox(value)

    @field_validator("context")
    @classmethod
    def vm_context(cls, value: str) -> str:
        return validate_vm_context(value)


class VoicemailUserUnbindResponse(BaseModel):
    user_id: str
    mailbox: str | None = None
    context: str
    unlinked: bool = True
