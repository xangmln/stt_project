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

@user.get("", response_model=list[User])
async def get_all_user(db = Depends(get_db)):
    users_col = db["users"]
    cursor = users_col.find({}).sort("created_at", -1)  # 최신순 정렬(옵션)
    return [User.model_validate(doc) async for doc in cursor]


@user.post("", response_model=User)
async def create_user(payload: UserIn, db = Depends(get_db)):
    users = db["users"]

    # User 객체 생성 (created_at 자동 세팅됨)
    user_doc = User(**payload.model_dump())

    res = await users.insert_one(user_doc.model_dump(by_alias=True, exclude_none=True))
    created = await users.find_one({"_id": res.inserted_id})

    return User.model_validate(created)

@user.get("/{id}", response_model=User)
async def get_user(id: str, db = Depends(get_db)):
    if not ObjectId.is_valid(id):
        raise HTTPException(400, "Invalid ObjectId format")
    users = db["users"]
    doc = await users.find_one({"_id": ObjectId(id)})
    return to_user(doc)


@user.put("/{user_id}", response_model=User)
async def update_agent_id(user_id: str, agent_id: str, db=Depends(get_db)):
    if not ObjectId.is_valid(user_id):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    users = db["users"]
    res = await users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"agent_id": agent_id}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    updated = await users.find_one({"_id": ObjectId(user_id)})
    return User.model_validate(updated)