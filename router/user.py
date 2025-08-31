from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from typing import Any, Dict

from core.db import get_db
from schema.user import UserIn, User

user = APIRouter(prefix="/user", tags=["user"])

def to_user(doc: Dict[str, Any]) -> User:
    if not doc:
        raise HTTPException(404, "User not found")
    doc["_id"] = str(doc["_id"])  # ObjectId -> str
    return User.model_validate(doc)

# --- [수정됨] GET (전체): is_deleted가 True가 아닌 사용자만 조회 ---
@user.get("", response_model=list[User])
async def get_all_user(db = Depends(get_db)):
    """
    모든 유저 출력
    """
    users_col = db["users"]
    
    # is_deleted가 True가 아닌 (즉, False이거나 필드가 없는) 사용자만 찾도록 필터 추가
    query = {"is_deleted": {"$ne": True}}
    
    cursor = users_col.find(query).sort("created_at", -1)
    return [User.model_validate(doc) async for doc in cursor]


@user.post("", response_model=User)
async def create_user(payload: UserIn, db = Depends(get_db)):
    """
    유저 생성
    """
    users = db["users"]

    # User 객체 생성 (created_at 자동 세팅됨)
    user_doc = User(**payload.model_dump())

    res = await users.insert_one(user_doc.model_dump(by_alias=True, exclude_none=True))
    created = await users.find_one({"_id": res.inserted_id})

    return User.model_validate(created)

# --- [수정됨] GET (ID로 조회): is_deleted가 True가 아닌 사용자만 조회 ---
@user.get("/{id}", response_model=User)
async def get_user_by_id(id: str, db = Depends(get_db)): # 함수 이름 변경 (중복 방지)
    """
    id로 유저 한명 출력
    """
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "Invalid ObjectId format")

    users = db["users"]
    
    # 조회 조건에 is_deleted 필터 추가
    query = {"_id": ObjectId(id), "is_deleted": {"$ne": True}}
    
    doc = await users.find_one(query)
    
    # doc이 없으면 (ID가 없거나, 있더라도 is_deleted=True인 경우) 404 에러
    if not doc:
        raise HTTPException(404, "User not found or has been deleted")

    return User.model_validate(doc)


# --- [수정됨] GET (phone_id로 조회): is_deleted가 True가 아닌 사용자만 조회 ---
@user.get("/phone/{phone_id}", response_model=User)
async def get_user_by_phone_id(phone_id: str, db = Depends(get_db)): # 함수 이름 변경 (중복 방지)
    """
    기기 id로 유저 한명 출력
    """
    users = db["users"]

    # 조회 조건에 is_deleted 필터 추가
    query = {"phone_id": phone_id, "is_deleted": {"$ne": True}}
    
    user_doc = await users.find_one(
        query,
        sort=[("created_at", -1), ("_id", -1)],
        projection={
            "_id": 1,
            "agent_id": 1,
            "phone_id": 1,
            "created_at": 1,
            "is_deleted": 1, # is_deleted 필드도 함께 가져오도록 추가 (선택)
        },
    )
    
    if not user_doc:
        raise HTTPException(
            status_code=404,
            detail="User with this phone_id not found or has been deleted"
        )
    
    return User.model_validate(user_doc)

@user.put("/{user_id}/logout")
async def logout_user_by_id(user_id: str, db = Depends(get_db)):
    """
    지정된 user_id를 가진 사용자의 is_deleted를 True로 설정
    """
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user_id format"
        )
        
    users_col = db["users"]

    res = await users_col.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"is_deleted": True}}
    )

    if res.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    return
