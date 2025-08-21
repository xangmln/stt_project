# stt.py
import os
from pathlib import Path
from typing import List, Tuple, Dict, Any
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("ELEVENLABS_API_KEY")
MODEL_ID = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")

def _to_dict(x: Any) -> Dict[str, Any]:
    """Pydantic 모델/일반 dict를 공통 dict로 정규화"""
    if hasattr(x, "model_dump"):  # pydantic v2
        return x.model_dump()
    if isinstance(x, dict):
        return x
    # 안전장치: getattr로 자주 쓰는 필드만 뽑기
    return {
        "text": getattr(x, "text", None),
        "start": getattr(x, "start", None),
        "end": getattr(x, "end", None),
        "speaker_id": getattr(x, "speaker_id", None) or getattr(x, "speaker", None),
    }

def transcribe_speeches(audio_path: str | Path, expected_speakers: int = 2) -> List[Tuple[str, str]]:
    """
    m4a/mp3/wav → ElevenLabs STT(diarize) → [(speech1, "대사..."), (speech2, "대사..."), ...]
    - 화자 라벨은 '등장 순서'대로 speech1, speech2에 동적 매핑
    - 동일 화자가 연속이면 한 턴으로 합쳐서 반환
    """
    if not API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY가 .env에 없습니다.")
    p = Path(audio_path)
    if not p.exists():
        raise FileNotFoundError(f"파일이 없습니다: {p.resolve()}")

    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=API_KEY)

    with p.open("rb") as f:
        resp = client.speech_to_text.convert(
            file=f,
            model_id=MODEL_ID,
            diarize=True,
            num_speakers=expected_speakers,     # 2명 가정
            timestamps_granularity="word",      # 단어 단위 타임스탬프/화자
            language_code="ko",                 # (선택) 한국어 명시
        )

    # words 또는 segments 중 있는 쪽을 사용
    words = getattr(resp, "words", None)
    segments = getattr(resp, "segments", None)

    # 1) segments에 speaker 정보가 잘 붙는 계정이라면 이게 더 안정적
    if segments:
        segs = [_to_dict(s) for s in segments]
        return _group_and_map_by_speaker(segs, field_text="text", field_speaker="speaker_id")

    # 2) 그 외엔 word 단위에서 speaker 추정
    if words:
        ws = [_to_dict(w) for w in words]
        # 단어들을 같은 화자 기준으로 문장으로 합치기
        merged_by_speaker = []
        cur_spk = None
        buf = []
        for w in ws:
            spk = w.get("speaker_id")
            token = (w.get("text") or "").strip()
            if not token:
                continue
            if spk != cur_spk and buf:
                merged_by_speaker.append({"speaker_id": cur_spk, "text": " ".join(buf)})
                buf = []
            cur_spk = spk
            buf.append(token)
        if buf:
            merged_by_speaker.append({"speaker_id": cur_spk, "text": " ".join(buf)})
        return _group_and_map_by_speaker(merged_by_speaker, field_text="text", field_speaker="speaker_id")

    # 3) 최후 수단: 전체 텍스트만 있을 때
    whole = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None)
    if not whole:
        raise RuntimeError(f"STT 결과를 해석할 수 없습니다: {type(resp)}")
    return [("speech1", whole.strip())]

def _group_and_map_by_speaker(items: List[Dict[str, Any]], *, field_text: str, field_speaker: str) -> List[Tuple[str, str]]:
    """
    items: [{"speaker_id": raw_id, "text": "..."} ...] 형태를 받아
    - raw speaker id 등장 순서대로 {"raw_id" -> "speech1"/"speech2"} 매핑
    - 연속 같은 speechX는 한 턴으로 합쳐서 반환
    """
    # 1) raw speaker id -> speechX 동적 매핑
    label_order = ["speech1", "speech2", "speech3", "speech4"]  # 확장 가능
    mapping: Dict[str, str] = {}
    next_idx = 0

    def map_label(raw):
        nonlocal next_idx
        key = str(raw) if raw is not None else "__unknown__"
        if key not in mapping:
            mapping[key] = label_order[min(next_idx, len(label_order)-1)]
            next_idx += 1
        return mapping[key]

    # 2) 턴 병합
    turns: List[Tuple[str, str]] = []
    cur_label = None
    buf: List[str] = []
    for it in items:
        raw_spk = it.get(field_speaker)
        label = map_label(raw_spk)
        txt = (it.get(field_text) or "").strip()
        if not txt:
            continue
        if label != cur_label and buf:
            turns.append((cur_label, " ".join(buf).strip()))
            buf = []
        cur_label = label
        buf.append(txt)
    if buf:
        turns.append((cur_label, " ".join(buf).strip()))
    return turns
