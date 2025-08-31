import os
import json
import base64
import requests
from dotenv import load_dotenv

from langsmith import Client
from langchain_core.messages import HumanMessage
from langchain_google_genai import GoogleGenerativeAI

load_dotenv()

PROMPT_NAME = os.getenv("LANGSMITH_PROMPT_NAME")  # LangSmith에 저장된 프롬프트 이름

def google_evaluate_text(audio_path_or_url: str, report, is_url: bool = False) -> str:
    """
    LangSmith에 저장된 프롬프트를 불러와서 오디오(base64) 넣고 실행.
    audio_path_or_url: 파일 경로나 fixed url
    is_url: True면 URL에서 다운받아서 사용
    """
    if not PROMPT_NAME:
        raise RuntimeError("LANGSMITH_PROMPT_NAME(.env)이 필요합니다.")
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY(.env)이 필요합니다.")

    # 1) LangSmith 프롬프트 가져오기
    client = Client()
    prompt = client.pull_prompt(PROMPT_NAME, include_model=True)

    # 2) 오디오 로딩
    if is_url:
        resp = requests.get(audio_path_or_url)
        if resp.status_code != 200:
            raise RuntimeError(f"파일을 가져오지 못했습니다. status={resp.status_code}")
        audio_bytes = resp.content
    else:
        with open(audio_path_or_url, "rb") as f:
            audio_bytes = f.read()

    encoded_audio = base64.b64encode(audio_bytes).decode("utf-8")

    audio_file = HumanMessage(content=[
        {
            "type": "audio",
            "source_type": "base64",
            "data": encoded_audio,
            "mime_type": "audio/mp4",  # 확장자에 맞춰 변경 가능 (m4a → audio/mp4)
        },
    ])

    # 3) 실행
    chain = prompt
    result = chain.invoke({"audio_file": [audio_file], "prev_report": report})

    return result
