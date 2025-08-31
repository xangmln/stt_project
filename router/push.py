# routers/push.py

# 1. 필요한 라이브러리들을 가져옵니다.
from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId  # MongoDB의 고유 ID를 다루기 위함
from firebase_admin import messaging  # Firebase 푸시 알림 기능을 사용하기 위함

# 2. 우리 프로젝트의 다른 모듈들을 가져옵니다.
from core.db import get_db  # 데이터베이스 연결을 가져오는 함수
from schema.user import User  # 사용자 데이터의 형태를 정의한 스키마

# 3. FastAPI의 APIRouter를 생성합니다.
# 이 라우터에 등록된 모든 API는 주소 앞에 /push가 붙게 됩니다.
push = APIRouter(prefix="/push", tags=["push"])


# 4. API 엔드포인트를 정의합니다.
# 웹에서 POST 방식으로 /push/{상담원ID}/{고객번호} 형태의 주소를 호출하면 이 함수가 실행됩니다.
@push.post("")
async def send_call_notification(
    user_id: str,
    customer_phone_number: str,
    customer_name: str,
    db=Depends(get_db)  # FastAPI의 의존성 주입 기능으로 DB 연결을 얻어옵니다.
):
    """
    지정된 상담원에게 고객의 전화번호(customer_phone_number)와 함께
    '통화 걸기' 푸시 알림 전송.
    """

    # --- 5. 상담원 정보 조회 ---
    print(f"푸시 알림 요청 수신: 상담원 ID({user_id}), 고객 번호({customer_phone_number})")

    # MongoDB의 ObjectId는 정해진 형식이 있으므로, 먼저 유효한 형식인지 확인합니다.
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="올바르지 않은 상담원 ID 형식입니다.")

    # 데이터베이스의 'users' 컬렉션에서 해당 ID를 가진 상담원을 찾습니다.
    users_collection = db["users"]
    user_document = await users_collection.find_one({"_id": ObjectId(user_id)})

    # 상담원이 존재하지 않으면, 404 Not Found 에러를 반환하고 함수를 종료합니다.
    if not user_document:
        raise HTTPException(status_code=404, detail="해당 상담원을 찾을 수 없습니다.")

    # 찾은 데이터를 User 스키마에 맞춰 변환합니다. 데이터 유효성 검사도 함께 이루어집니다.
    user = User.model_validate(user_document)

    # --- 6. 푸시 토큰 확인 ---
    # 상담원 정보에 푸시 토큰이 저장되어 있는지 확인합니다.
    if not user.push_token:
        # 토큰이 없으면 알림을 보낼 수 없으므로, 에러를 반환하고 함수를 종료합니다.
        raise HTTPException(
            status_code=400,
            detail=f"상담원 '{user.agent_id}'에게 등록된 푸시 토큰이 없습니다."
        )

    target_token = user.push_token
    print(f"알림 보낼 대상: {user.agent_id}, 토큰 앞 10자리: {target_token[:10]}...")

    # --- 7. 푸시 알림 메시지 생성 ---
    # Firebase에 보낼 메시지 객체를 만듭니다.
    message_to_send = messaging.Message(
        # [화면에 직접 표시될 내용]
        notification=messaging.Notification(
            title="📞 통화 걸기",  # 알림의 제목
            body=f"{customer_name} 님",  # 알림의 본문
        ),
        
        # [앱이 내부적으로 사용할 숨겨진 데이터]
        # 이 부분은 모바일 앱 개발자와 미리 약속해야 하는 매우 중요한 부분입니다.
        data={
            "type": "CALL_REQUEST",  # 알림의 종류를 나타내는 식별자
            "phoneToCall": customer_phone_number,  # 앱이 이 번호로 전화를 걸어야 함
        },
        
        # [알림을 보낼 대상 기기]
        token=target_token
    )

    # --- 8. 푸시 알림 발송 ---
    print("Firebase에 푸시 알림 발송을 요청합니다...")
    try:
        # 생성한 메시지를 Firebase 서버로 전송합니다.
        response = messaging.send(message_to_send)
        
        # 성공 시, Firebase가 반환하는 메시지 ID를 로그에 남깁니다.
        print(f"푸시 알림 발송 성공! Message ID: {response}")
        
        # 웹(호출한 쪽)에 성공 메시지를 반환합니다.
        return {
            "status": "success",
            "detail": f"'{user.agent_id}' 상담원에게 푸시 알림을 성공적으로 보냈습니다.",
            "firebase_message_id": response
        }
        
    except Exception as e:
        # 메시지 전송 중 오류가 발생한 경우 (예: 토큰이 만료됨)
        print(f"푸시 알림 발송 중 오류 발생: {e}")
        
        # 웹(호출한 쪽)에 실패 메시지와 함께 500 Server Error를 반환합니다.
        raise HTTPException(
            status_code=500,
            detail=f"푸시 알림 발송에 실패했습니다: {str(e)}"
        )