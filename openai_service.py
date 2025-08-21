# ls_service.py
from __future__ import annotations
import os
from dotenv import load_dotenv

import json

from langsmith import Client
from langchain_openai import ChatOpenAI

load_dotenv()

PROMPT_NAME = os.getenv("LANGSMITH_PROMPT_NAME")  # LangSmith에 저장된 프롬프트 이름

def openai_evaluate_text(text: str) -> str:
    """
    LangSmith에 이미 저장된 프롬프트(입력 변수: 'text')를 불러와,
    {text}만 넣어 LLM 실행 → 모델 응답 문자열만 반환.
    """
    if not PROMPT_NAME:
        raise RuntimeError("LANGSMITH_PROMPT_NAME(.env)이 필요합니다.")

    # 1) LangSmith 프롬프트 가져오기 (Hub/전역에 저장되어 있어야 함)
  
    client = Client()
    prompt = client.pull_prompt(PROMPT_NAME, include_model=False)  # 예: "consult-eval-v1" 또는 "owner/name:latest"
    
    # 2) LLM 연결 후 실행
    llm = ChatOpenAI(model="gpt-5-mini")  # OPENAI_API_KEY 자동 사용
    chain = prompt | llm
    result = chain.invoke({"text": text})

    return json.dumps({"message": result.content}, ensure_ascii=False, indent=2)
