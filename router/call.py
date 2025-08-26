

import os, uuid, mimetypes, asyncio
from anyio import to_thread
from datetime import timedelta
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, BackgroundTasks
from pydantic import ValidationError
from pymongo import ReturnDocument
from bson import ObjectId

from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv

from core.db import get_db
from schema.call import Call, Report, CallBrief
from schema.common import utcnow
from gemini_service import google_evaluate_text  # 평가 함수 (dict 반환 가정)

load_dotenv()

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY", "")
MINIO_SECURE   = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET   = os.getenv("MINIO_BUCKET", "chadamjin")
PUBLIC_BASE    = os.getenv("PUBLIC_BASE")


call = APIRouter(prefix="/call", tags=["call"])

mc = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS,
    secret_key=MINIO_SECRET,
    secure=MINIO_SECURE,
)

def guess_audio_type(name: str) -> str:
    ctype, _ = mimetypes.guess_type(name)
    return ctype or "audio/mpeg"


# 1) async 작업 함수 (재시도 + 상태 업데이트)
async def eval_and_update_call_retry(db, prev_report_text, call_id: str, eval_url: str,
                                     max_attempts: int = 3, base_delay_sec: int = 5):
    async def run_once(attempt: int) -> bool:
        await db["calls"].update_one(
            {"_id": ObjectId(call_id)},
            {"$set": {
                "evaluation_status": "running" if attempt == 1 else "retrying",
                "evaluation_attempts": attempt,
                "updated_at": utcnow(),
            }}
        )
        try:
            # 동기 함수 → 스레드에서 실행
            data = await to_thread.run_sync(google_evaluate_text, eval_url, prev_report_text, True)
            if not data:
                raise ValueError("evaluate_text returned None/empty")

            report = Report(**data)
            await db["calls"].update_one(
                {"_id": ObjectId(call_id)},
                {"$set": {
                    "report": report.model_dump(),
                    "evaluation_status": "done",
                    "updated_at": utcnow(),
                    "evaluation_last_error": None,
                }}
            )
            return True
        except Exception as e:
            await db["calls"].update_one(
                {"_id": ObjectId(call_id)},
                {"$set": {"evaluation_last_error": str(e), "updated_at": utcnow()}}
            )
            return False

    for attempt in range(1, max_attempts + 1):
        if await run_once(attempt):
            return
        if attempt < max_attempts:
            await asyncio.sleep(base_delay_sec * (2 ** (attempt - 1)))

    await db["calls"].update_one(
        {"_id": ObjectId(call_id)},
        {"$set": {"evaluation_status": "failed", "updated_at": utcnow()}}
    )


# 2) BackgroundTasks가 호출할 동기 브리지
def schedule_eval_from_thread(db, prev_report_text, call_id: str, eval_url: str,
                              max_attempts: int, base_delay_sec: int):
    import anyio
    # 스레드에서 메인 루프로 코루틴 실행
    anyio.from_thread.run(
        eval_and_update_call_retry,
        db, prev_report_text, call_id, eval_url, max_attempts, base_delay_sec
    )



@call.post("", response_model=Call)
async def create_call(
    background: BackgroundTasks,
    user_id: str = Form(...),
    customer_num: str = Form(...),
    file: UploadFile = File(...),
    db_dep = Depends(get_db),
):
    # 0) user 확인
    if not ObjectId.is_valid(user_id):
        raise HTTPException(400, "Invalid user_id(ObjectId string)")

    user_doc = await db_dep["users"].find_one({"_id": ObjectId(user_id)}, {"agent_id": 1})
    if not user_doc:
        raise HTTPException(404, "User not found")
    agent_id = user_doc.get("agent_id")

    # 1) 오디오 체크
    if not (file.content_type or "").startswith("audio"):
        raise HTTPException(400, "오디오 파일만 허용됩니다.")

    # 2) 업로드
    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    object_name = f"{uuid.uuid4().hex}{ext}"
    content_type = file.content_type or guess_audio_type(file.filename or "audio")

    try:
        mc.put_object(
            MINIO_BUCKET,
            object_name,
            data=file.file,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=content_type,
        )
    except S3Error as e:
        raise HTTPException(500, f"MinIO 업로드 실패: {e}")

    fixed_url = f"{PUBLIC_BASE}/{MINIO_BUCKET}/{object_name}"
    eval_url = fixed_url

   # 3) create_call 내부 변경 부분만
    # 3) call_count: (user_id, customer_num) 최신값 + 1 로 계산
    latest = await db_dep["calls"].find_one(
        {"user_id": user_id, "customer_num": customer_num},
        sort=[("call_count", -1)],
        projection={"call_count": 1},
    )
    next_count = (int(latest.get("call_count", 0)) + 1) if latest else 1

    # ✅ 바로 이전 통화 1건의 report만 추출 → 문자열로 변환
    if next_count > 1:
        prev_doc = await db_dep["calls"].find_one(
            {"user_id": user_id, "customer_num": customer_num},
            sort=[("call_count", -1)],
            projection={"report": 1, "call_count": 1}
        )
        prev_report = (prev_doc or {}).get("report")
        # 프롬프트에 넣기 좋게 JSON 문자열로 직렬화 (원하면 커스텀 포맷으로 변경 가능)
        prev_report_text = json.dumps(prev_report, ensure_ascii=False) if prev_report else ""
    else:
        prev_report_text = ""  # 이전 통화 없음

    # 4) 콜 문서 우선 저장 (report 없음, pending)
    doc = Call(
        user_id=user_id,
        agent_id=agent_id,
        report=None,
        created_at=utcnow(),
        call_count=next_count,
        customer_num=customer_num,
        url=fixed_url,
        evaluation_status="pending",
        evaluation_attempts=0
    )
    res = await db_dep["calls"].insert_one(doc.model_dump(by_alias=True, exclude_none=True))
    call_id = str(res.inserted_id)

    # 5) 백그라운드 재시도 작업 등록 (최대 3회, 5s/10s/20s 백오프 예시)
    # ✅ 백그라운드에서 평가 실행 (동기 브리지를 등록)
    background.add_task(
        schedule_eval_from_thread, db_dep, prev_report_text, call_id, eval_url, 3, 5
    )

    # 6) 즉시 응답
    created = await db_dep["calls"].find_one({"_id": ObjectId(call_id)})
    return Call.model_validate(created)

# 1) call_id로 단일 문서 조회
@call.get("/{call_id}", response_model=Call)
async def get_call_by_id(call_id: str, db=Depends(get_db)):
    if not ObjectId.is_valid(call_id):
        raise HTTPException(status_code=400, detail="Invalid call_id")

    calls = db["calls"]
    doc = await calls.find_one({"_id": ObjectId(call_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Call not found")

    return Call.model_validate(doc)


# 2) user_id로 해당 유저의 모든 call 조회 (요약 버전)
@call.get("/user/{user_id}", response_model=list[CallBrief])
async def get_calls_by_user(user_id: str, db=Depends(get_db)):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    calls = db["calls"]

    # ✅ 필요한 필드만 projection
    cursor = calls.find(
        {"user_id": str(user_id)},
        projection={
            "user_id": 1,
            "agent_id": 1,
            "created_at": 1,
            "call_count": 1,
            "customer_num": 1,
            "url": 1,
            "evaluation_status": 1,
            "evaluation_attempts": 1,
            "evaluation_last_error": 1,
            "report.overall_score": 1,
            "report.keyword": 1,
            "report.is_valid": 1,
        }
    ).sort("created_at", -1)

    results = [CallBrief.model_validate(doc) async for doc in cursor]

    if not results:
        raise HTTPException(status_code=404, detail="No calls found for this user")

    return results

