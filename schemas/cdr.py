from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class CDRRecord(BaseModel):

    dst: str
    start: datetime
    userfield: Optional[str]=None
    dcontext: str
    answer: datetime
    sequence: int
    clid: str
    end: datetime
    channel: str
    duration: int
    dstchannel: Optional[str]=None
    billsec: int
    lastapp: str
    disposition: str
    src: str
    lastdata: Optional[str]=None
    amaflags: int
    accountcode: Optional[int]=None
    uniqueid: str #name-id
    
    model_config = ConfigDict(from_attributes=True)

class CDRInputData(BaseModel):
    # instance_name: str
    src: Optional[str] = None
    dst: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    limit: int = 100
    offset: int = 0