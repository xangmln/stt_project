# ls_service.py
from __future__ import annotations
import os
import json
from dotenv import load_dotenv

from langsmith import Client
from langchain_google_genai import ChatGoogleGenerativeAI  # ← 변경 포인트

load_dotenv()

PROMPT_NAME = os.getenv("LANGSMITH_PROMPT_NAME")  # LangSmith에 저장된 프롬프트 이름

def google_evaluate_text(text: str) -> str:
    """
    LangSmith에 이미 저장된 프롬프트(입력 변수: 'text')를 불러와,
    {text}만 넣어 LLM 실행 → 모델 응답 문자열만 반환.
    """
    if not PROMPT_NAME:
        raise RuntimeError("LANGSMITH_PROMPT_NAME(.env)이 필요합니다.")
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY(.env)이 필요합니다.")

    # 1) LangSmith 프롬프트 가져오기 (Hub/전역에 저장되어 있어야 함)
    client = Client()
    prompt = client.pull_prompt(PROMPT_NAME, include_model=False)

    # 2) LLM 연결 (Gemini 2.5‑flash)
    # 필요 시 temperature, max_output_tokens 등 추가 가능
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.2,
    )

    # 3) 실행
    chain = prompt | llm
    result = chain.invoke({"text": text})

    # 4) 동일한 반환 포맷 유지
    return json.dumps({"message": result.content}, ensure_ascii=False, indent=2)
