import os, uuid, mimetypes, asyncio, json
from anyio import to_thread
from datetime import timedelta, datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, BackgroundTasks, Query
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

MINIO_ENDPOINT = "chadamjin.tail3de323.ts.net:9000"
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY", "")
MINIO_SECURE   = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET   = os.getenv("MINIO_BUCKET", "chadamjin")
PUBLIC_BASE    = "http://chadamjin.tail3de323.ts.net:9000"


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
    phone_id: str = Form(...),
    customer_num: str = Form(...),
    customer_name: str = Form(...),
    file: UploadFile = File(...),
    db_dep = Depends(get_db),
):
    """
    통화기록 데이터 생성
    """
    # 0) phone_id로 유저 확인 (가장 최근 생성된 user 선택)
    user_doc = await db_dep["users"].find_one(
        {"phone_id": phone_id},
        sort=[("created_at", -1), ("_id", -1)],
        projection={"_id": 1, "agent_id": 1}
    )
    if not user_doc:
        raise HTTPException(404, "User with this phone_id not found")

    user_id = str(user_doc["_id"])
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
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))

    today_str = now_kst.today().strftime("%Y-%m/%d")
    full_object_path = f"{today_str}/{object_name}"

    try:
        mc.put_object(
            MINIO_BUCKET,
            full_object_path,
            data=file.file,
            length=-1,
            part_size=10 * 1024 * 1024,
            content_type=content_type,
        )
    except S3Error as e:
        raise HTTPException(500, f"MinIO 업로드 실패: {e}")

    
    fixed_url = f"{PUBLIC_BASE}/{MINIO_BUCKET}/{full_object_path}"
    eval_url = fixed_url

    # 3) call_count: (user_id, customer_num) 최신값 + 1 로 계산
    latest = await db_dep["calls"].find_one(
        {"user_id": user_id, "customer_num": customer_num},
        sort=[("call_count", -1)],
        projection={"call_count": 1},
    )
    next_count = (int(latest.get("call_count", 0)) + 1) if latest else 1

    # ✅ 바로 이전 통화 1건의 report만 추출
    if next_count > 1:
        prev_doc = await db_dep["calls"].find_one(
            {"user_id": user_id, "customer_num": customer_num},
            sort=[("call_count", -1)],
            projection={"report": 1, "call_count": 1}
        )
        prev_report = (prev_doc or {}).get("report")
        prev_report_text = json.dumps(prev_report, ensure_ascii=False) if prev_report else ""
    else:
        prev_report_text = ""

    # 4) 콜 문서 우선 저장 (report 없음, pending)
    doc = Call(
        user_id=user_id,               # ✅ phone_id로 찾은 user_id를 저장
        agent_id=agent_id,
        report=None,
        created_at=utcnow(),
        call_count=next_count,
        customer_num=customer_num,
        customer_name=customer_name,
        url=fixed_url,
        evaluation_status="pending",
        evaluation_attempts=0
    )
    res = await db_dep["calls"].insert_one(doc.model_dump(by_alias=True, exclude_none=True))
    call_id = str(res.inserted_id)

    # 5) 백그라운드 평가 작업 등록
    background.add_task(
        schedule_eval_from_thread, db_dep, prev_report_text, call_id, eval_url, 3, 5
    )

    # 6) 즉시 응답
    created = await db_dep["calls"].find_one({"_id": ObjectId(call_id)})
    return Call.model_validate(created)

# 1) call_id로 단일 문서 조회
@call.get("/{call_id}", response_model=Call)
async def get_call_by_id(call_id: str, db=Depends(get_db)):
    """
    통화기록 id로 하나의 데이터객체 출력
    """
    if not ObjectId.is_valid(call_id):
        raise HTTPException(status_code=400, detail="Invalid call_id")

    calls = db["calls"]
    doc = await calls.find_one({"_id": ObjectId(call_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Call not found")

    return Call.model_validate(doc)


# 2) user_id로 해당 유저의 모든 call 조회 (요약 버전)
@call.get("/user/{user_id}", response_model=list[Call])
async def get_calls_by_user(user_id: str, db=Depends(get_db)):
    """
    해당 유저의 모든 통화기록 조회
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    calls = db["calls"]

    # ✅ 필요한 필드만 projection
    cursor = calls.find(
        {"user_id": str(user_id)},
    ).sort("created_at", -1)

    results = [Call.model_validate(doc) async for doc in cursor]

    if not results:
        raise HTTPException(status_code=404, detail="No calls found for this user")

    return results


@call.get("/user/{user_id}/paged", response_model=list[Call])
async def get_calls_by_user_paginated(
    user_id: str,
    page: int = Query(1, description="페이지 번호", gt=0),
    limit: int = Query(30, description="페이지 당 결과 수", gt=0, le=100),
    db=Depends(get_db)
):
    """
    해당 유저의 통화기록을 페이지네이션하여 조회 (기본 30개씩)
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    calls = db["calls"]

    # 페이지네이션을 위한 skip 값 계산
    skip = (page - 1) * limit

    # ✅ skip과 limit을 적용하여 쿼리
    cursor = calls.find(
        {"user_id": str(user_id)},
    ).sort("created_at", -1).skip(skip).limit(limit)

    results = [Call.model_validate(doc) async for doc in cursor]

    # 참고: 만약 첫 페이지(page=1)에서 결과가 없을 때만 404를 반환하고 싶다면 아래와 같이 수정할 수 있습니다.
    # if not results and page == 1:
    #     raise HTTPException(status_code=404, detail="No calls found for this user")

    return results

# 3) phone_id로 해당 유저의 모든 call 조회 (요약 버전)
@call.get("/phone/{phone_id}", response_model=list[Call])
async def get_calls_by_user(user_id: str, db=Depends(get_db)):
    """
    기기 아이디로 모든 통화기록 조회
    """
    users = db["users"]

    # phone_id로 유저 찾기 — 가장 최근 생성된 유저 1명 선택
    # created_at 정렬 우선, 없으면 _id 기준(생성시간)으로 보조 정렬
    user_doc = await users.find_one(
        {"phone_id": phone_id},
        sort=[("created_at", -1), ("_id", -1)],
        projection={"_id": 1}
    )
    if not user_doc:
        raise HTTPException(status_code=404, detail="User with this phone_id not found")

    user_id_str = str(user_doc["_id"])

    calls = db["calls"]

    # ✅ 필요한 필드만 projection
    cursor = calls.find(
        {"user_id": user_id_str}
    ).sort("created_at", -1)

    results = [Call.model_validate(doc) async for doc in cursor]

    if not results:
        raise HTTPException(status_code=404, detail="No calls found for this user")

    return results
