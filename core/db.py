from __future__ import annotations
import os
from typing import AsyncGenerator
from pymongo import ASCENDING, DESCENDING
from pymongo.server_api import ServerApi
from pymongo.errors import PyMongoError
from pymongo import AsyncMongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://mongo:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "chadamjin")

client = AsyncMongoClient(
    MONGO_URI,
    server_api=ServerApi(version="1", strict=True, deprecation_errors=True),
)

db = client[MONGO_DB_NAME]

users = db.get_collection("users")
calls = db.get_collection("calls")

async def ping() -> None:
    await client.admin.command("ping")

async def init_indexes() -> None:
    await users.create_index([("agent_id", ASCENDING)])
    await users.create_index([("phone_id", ASCENDING)])
    await calls.create_index([("user_id", ASCENDING)])
    await calls.create_index([("created_at", DESCENDING)])

async def init_db() -> None:
    try:
        await ping()
        await init_indexes()
    except PyMongoError as e:
        raise

async def close_db() -> None:
    await client.close()

async def get_db() -> AsyncGenerator:
    yield db
