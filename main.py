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
from router.call import call
from router.user import user
from router.admin import admin
load_dotenv()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 앱 시작 시 실행
    await init_db()
    yield
    # 앱 종료 시 실행
    await close_db()



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