from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class CDRRecord(BaseModel):
    id: int
    calldate: datetime
    clid: str
    src: str
    dst: str
    duration: int
    billsec: int
    disposition: str
    uniqueid: str
    userfield: str
    instance_name: str


class ActiveCall(BaseModel):
    id: int
    uniqueid: str
    channel: str
    src: str
    dst: str
    state: str
    start_time: datetime
    instance_name: str


class CallFilter(BaseModel):
    instance_name: Optional[str] = None
    src: Optional[str] = None
    dst: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    limit: int = 100
    offset: int = 0


class AsteriskInstanceCreate(BaseModel):
    name: str
    sip_port: int
    http_port: int


class AsteriskInstanceResponse(BaseModel):
    id: int
    name: str
    sip_port: int
    http_port: int
    status: str

    class Config:
        orm_mode = True


class ConfigUpdate(BaseModel):
    config_type: str  # sip, extensions, etc.
    content: str


class SIPUserCreate(BaseModel):
    username: str
    password: str
    caller_id: str
    account_code: str = ""
    context: str = "internal"
    instance_name: str


class SIPUserUpdate(BaseModel):
    password: Optional[str] = None
    caller_id: Optional[str] = None
    account_code: Optional[str] = None
    context: Optional[str] = None
    is_active: Optional[bool] = None


class SIPUserResponse(BaseModel):
    id: int
    username: str
    caller_id: str
    account_code: str
    context: str
    instance_name: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CDRRecordWithUsers(BaseModel):
    id: int
    calldate: datetime
    src: str
    dst: str
    src_user: Optional[SIPUserResponse] = None
    dst_user: Optional[SIPUserResponse] = None
    duration: int
    billsec: int
    disposition: str
    accountcode: str
    dcontext: str
    instance_name: str
