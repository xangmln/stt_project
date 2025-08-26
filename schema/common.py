# schema/common.py
from __future__ import annotations
from typing import Optional, Union
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from bson import ObjectId
from pydantic import BaseModel, Field, field_serializer, field_validator, ValidationInfo

class PyObjectId(ObjectId):
    """Pydantic v2에서 MongoDB ObjectId를 안전하게 다루기 위한 래퍼."""
    @classmethod
    def __get_pydantic_core_schema__(cls, *_args, **_kwargs):
        from pydantic_core import core_schema

        def validate(v):
            if isinstance(v, ObjectId):
                return v
            if isinstance(v, str) and ObjectId.is_valid(v):
                return ObjectId(v)
            raise ValueError("Invalid ObjectId")

        return core_schema.no_info_after_validator_function(
            validate, core_schema.any_schema()
        )

class MongoBaseModel(BaseModel):
    """공통 베이스: _id(=ObjectId) 직렬화/역직렬화 처리 및 기본 설정."""
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    model_config = {
        "populate_by_name": True,     # alias로도/실명으로도 입력 허용
        "from_attributes": True,      # ORM 호환
        "arbitrary_types_allowed": True,
    }

    @field_serializer("id")
    def serialize_object_id(self, v: Optional[PyObjectId], _info):
        return str(v) if v else None

    @property
    def id_datetime(self) -> Optional[datetime]:
        """_id(ObjectId)의 생성 시각(UTC). 없으면 None."""
        if self.id:
            # generation_time은 aware UTC datetime
            return self.id.generation_time.astimezone(timezone.utc)
        return None

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def objectid_datetime(oid_like: Union[str, ObjectId, PyObjectId, None]) -> Optional[datetime]:
    """임의의 ObjectId/문자열에서 생성 시각(UTC) 추출."""
    if oid_like is None:
        return None
    if isinstance(oid_like, ObjectId):
        return oid_like.generation_time.astimezone(timezone.utc)
    if isinstance(oid_like, str) and ObjectId.is_valid(oid_like):
        return ObjectId(oid_like).generation_time.astimezone(timezone.utc)
    return None


KST = ZoneInfo("Asia/Seoul")

class CreatedAtKSTMixin:
    created_at: datetime

    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime, _info):
        if v is None:
            return None
        return v.astimezone(KST).isoformat()

class CreatedAtFromObjectIdMixin(BaseModel):
    """
    이 믹스인을 스키마에 섞으면(created_at 필드가 있을 때),
    created_at이 명시되지 않은 경우 _id(ObjectId)의 생성 시각으로 자동 설정합니다.
    예)
      class User(MongoBaseModel, CreatedAtFromObjectIdMixin):
          created_at: Optional[datetime] = None
          ...
    """
    created_at: Optional[datetime] = None

    @field_validator("created_at", mode="before")
    @classmethod
    def fill_created_at_from_id(cls, v, info: ValidationInfo):
        if v is not None:
            return v
        # _id 혹은 id에서 ObjectId를 찾아 생성시각 사용
        id_val = info.data.get("_id") or info.data.get("id")
        dt = objectid_datetime(id_val)
        return dt if dt is not None else v
