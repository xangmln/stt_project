# app.py
import os, uuid, mimetypes
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from minio import Minio
from minio.error import S3Error
from dotenv import load_dotenv
from gemini_service import google_evaluate_text
from contextlib import asynccontextmanager
from core.db import init_db, close_db
from core.firebase import setup_firebase
from router.call import call
from router.user import user
from router.admin import admin
from router.push import push
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 실행될 로직
    print("🚀 FastAPI application starting up...")
    
    # 1. 데이터베이스 초기화
    await init_db()
    print("✅ Database initialized.")
    
    # --- [3. 추가] Firebase Admin SDK 초기화 ---
    try:
        setup_firebase()
        print("✅ Firebase Admin SDK initialized.")
    except Exception as e:
        print(f"❌ Failed to initialize Firebase Admin SDK: {e}")
        # Firebase 초기화 실패 시 서버를 시작하지 않으려면 여기서 exit()를 호출할 수도 있습니다.
    
    yield
    
    # 앱 종료 시 실행될 로직
    print("👋 FastAPI application shutting down...")
    await close_db()
    print("✅ Database connection closed.")

app = FastAPI(title="Audio Fixed URL Uploader", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 필요 시 제한
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user)
app.include_router(call)
app.include_router(admin)
app.include_router(push)