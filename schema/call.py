from __future__ import annotations
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime

from schema.common import MongoBaseModel, CreatedAtKSTMixin
# 대화 턴
class ConversationTurn(BaseModel):
    turn: int = Field(ge=0)
    text: str
    speaker_role: Literal["agent", "customer"]

# 평가 항목 상세
class CriteriaDetail(BaseModel):
    score: int = Field(ge=0, le=100)
    improvement: Optional[str] = None
    evidence: Optional[List[str]] = None
    description: Optional[str] = None

# 고정 키
CriteriaKey = Literal[
    "지역","방문일시","인사","적극적 응대","적극적 세일즈",
    "용도 및 구매시기","문의 차량 확인","결제방법","차량안내",
]

# report 블록
class Report(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    conversation_list: List[ConversationTurn] = Field(default_factory=list)
    summary: str
    keyword: List[str] = Field(default_factory=list)
    is_valid: bool
    feedback: Optional[str] = None
    criteria: Dict[CriteriaKey, CriteriaDetail]

# 콜 문서: created_at은 비어있으면 _id의 시간으로 자동 설정
class Call(MongoBaseModel, CreatedAtKSTMixin):
    user_id: str = Field(..., description="users._id (문자열) 보관")
    agent_id: str
    report: Optional[Report] = None
    created_at: Optional[datetime] = None
    call_count: int = Field(ge=1)
    customer_num: str
    url: str
    evaluation_status: str = "pending"              # "pending" | "running" | "retrying" | "done" | "failed"
    evaluation_attempts: int = 0   
    evaluation_last_error: Optional[str] = None


class ReportBrief(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    keyword: List[str] = []
    is_valid: bool

class CallBrief(MongoBaseModel):
    user_id: str
    agent_id: str
    report: Optional[ReportBrief] = None   # pending인 경우 None일 수 있음
    created_at: datetime
    call_count: int
    customer_num: str
    url: str
    evaluation_status: str = "pending"
    evaluation_attempts: int = 0
    evaluation_last_error: Optional[str] = None
