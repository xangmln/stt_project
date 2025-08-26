from fastapi import APIRouter, Depends, HTTPException
from core.db import get_db

admin = APIRouter(prefix="/admin", tags=["admin"])

# 모든 user 삭제
@admin.delete("/users")
async def delete_all_users(db=Depends(get_db)):
    res = await db["users"].delete_many({})
    return {"deleted_count": res.deleted_count}

# 모든 call 삭제
@admin.delete("/calls")
async def delete_all_calls(db=Depends(get_db)):
    res = await db["calls"].delete_many({})
    return {"deleted_count": res.deleted_count}