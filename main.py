import os

import sys
from stt import transcribe_speeches
from openai_service import openai_evaluate_text
from gemini_service import google_evaluate_text
def main():
    if len(sys.argv) < 2:
        print("사용법: python main.py <음성.m4a>")
        raise SystemExit(2)

    audio_path = sys.argv[1]

    # STT → 화자 분리 텍스트(speech1/speech2)
    turns = transcribe_speeches(audio_path, expected_speakers=2)
    text = "\n".join(f"[{t['start']}-{t['end']}] {t['speaker']}: {t['text']}" for t in turns)

    # LangSmith 프롬프트 실행 → 모델 응답만 출력
    response = google_evaluate_text(text)
    print(response)
    return response

if __name__ == "__main__":
    main()