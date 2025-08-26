from __future__ import annotations
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field

from schema.common import MongoBaseModel, utcnow, CreatedAtKSTMixin

# 입력 스키마: agent_id, created_at만 (created_at은 선택)
class UserIn(BaseModel):
    agent_id: str = Field(..., min_length=1)
    phone_id: Optional[str] = None

# 저장/응답 스키마: _id(ObjectId), agent_id, phone_id, created_at
class User(MongoBaseModel, CreatedAtKSTMixin):
    agent_id: str
    phone_id: Optional[str] = None
    created_at: datetime = Field(default_factory=utcnow)  # 비어있으면 _id 시간으로 자동 세팅
