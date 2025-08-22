# stt.py
import os
from pathlib import Path
from typing import List, Tuple, Dict, Any, Union
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("ELEVENLABS_API_KEY")
MODEL_ID = os.getenv("ELEVENLABS_STT_MODEL", "scribe_v1")

def _to_dict(x: Any) -> Dict[str, Any]:
    """Pydantic 모델/일반 dict를 공통 dict로 정규화"""
    if hasattr(x, "model_dump"):  # pydantic v2
        d = x.model_dump()
    elif isinstance(x, dict):
        d = x
    else:
        d = {
            "text": getattr(x, "text", None),
            "start": getattr(x, "start", None),
            "end": getattr(x, "end", None),
            "speaker_id": getattr(x, "speaker_id", None) or getattr(x, "speaker", None),
        }
    # 필드 표준화
    return {
        "text": d.get("text"),
        "start": d.get("start"),
        "end": d.get("end"),
        "speaker_id": d.get("speaker_id") or d.get("speaker"),
    }

def _label_mapper():
    """raw speaker id -> speechX 라벨 동적 매퍼"""
    label_order = ["speech1", "speech2", "speech3", "speech4"]
    mapping: Dict[str, str] = {}
    next_idx = 0

    def map_label(raw) -> str:
        nonlocal next_idx
        key = str(raw) if raw is not None else "__unknown__"
        if key not in mapping:
            mapping[key] = label_order[min(next_idx, len(label_order)-1)]
            next_idx += 1
        return mapping[key]
    return map_label

def _merge_items_by_speaker(
    items: List[Dict[str, Any]],
    *,
    field_text: str = "text",
    field_speaker: str = "speaker_id",
    field_start: str = "start",
    field_end: str = "end",
) -> List[Dict[str, Union[str, float]]]:
    """
    같은 화자가 연속으로 말한 조각을 하나의 '턴'으로 병합.
    각 턴에 start/end(초)를 포함.
    """
    map_label = _label_mapper()

    turns: List[Dict[str, Union[str, float]]] = []
    cur_label: Union[str, None] = None
    buf_text: List[str] = []
    turn_start: Union[float, None] = None
    turn_end: Union[float, None] = None

    def flush():
        nonlocal buf_text, turn_start, turn_end, cur_label
        if buf_text and cur_label is not None:
            turns.append({
                "speaker": cur_label,
                "text": " ".join(buf_text).strip(),
                "start": float(turn_start) if turn_start is not None else None,
                "end": float(turn_end) if turn_end is not None else None,
            })
        buf_text = []
        turn_start = None
        turn_end = None

    for it in items:
        raw_spk = it.get(field_speaker)
        label = map_label(raw_spk)
        txt = (it.get(field_text) or "").strip()
        s = it.get(field_start)
        e = it.get(field_end)

        if not txt:
            continue

        if label != cur_label:
            # 라벨이 바뀌면 기존 턴 확정
            flush()
            cur_label = label
            buf_text = [txt]
            turn_start = s
            turn_end = e
        else:
            # 같은 화자면 이어붙임
            buf_text.append(txt)
            # 시작시간은 기존 유지, 종료시간은 최신으로 갱신
            if turn_start is None and s is not None:
                turn_start = s
            if e is not None:
                turn_end = e

    # 마지막 턴 flush
    flush()

    # 보기 좋게 소수점 2자리로 반올림(원하면 제거 가능)
    for t in turns:
        if isinstance(t.get("start"), float):
            t["start"] = round(t["start"], 2)
        if isinstance(t.get("end"), float):
            t["end"] = round(t["end"], 2)

    return turns

def transcribe_speeches(audio_path: str | Path, expected_speakers: int = 2) -> List[Dict[str, Union[str, float]]]:
    """
    m4a/mp3/wav → ElevenLabs STT(diarize) →
    [
      {"speaker": "speech1", "text": "...", "start": 0.12, "end": 2.34},
      {"speaker": "speech2", "text": "...", "start": 2.50, "end": 5.10},
      ...
    ]
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
            num_speakers=expected_speakers,
            timestamps_granularity="word",  # 'segment'로 바꾸고 싶으면 여기만 교체
            language_code="ko",
        )

    words = getattr(resp, "words", None)
    segments = getattr(resp, "segments", None)

    # 1) segment 기반(있으면 이게 더 안정적: 보통 문장/구 단위, start/end 포함)
    if segments:
        segs = [_to_dict(s) for s in segments]
        return _merge_items_by_speaker(
            segs,
            field_text="text",
            field_speaker="speaker_id",
            field_start="start",
            field_end="end",
        )

    # 2) word 기반(단어들을 같은 화자 기준으로 묶으면서 start/end 계산)
    if words:
        ws = [_to_dict(w) for w in words]
        # word → 작은 조각으로 먼저 묶어 준 뒤(연속 화자), 그 결과를 merge 함수에 태워 동일 로직
        merged_small: List[Dict[str, Any]] = []
        cur_spk = None
        buf: List[str] = []
        start = None
        end = None

        def flush_small():
            nonlocal buf, start, end, cur_spk
            if buf:
                merged_small.append({
                    "speaker_id": cur_spk,
                    "text": " ".join(buf).strip(),
                    "start": start,
                    "end": end,
                })
            buf = []
            start = None
            end = None

        for w in ws:
            spk = w.get("speaker_id")
            token = (w.get("text") or "").strip()
            s = w.get("start")
            e = w.get("end")
            if not token:
                continue
            if spk != cur_spk:
                flush_small()
                cur_spk = spk
                buf = [token]
                start = s
                end = e
            else:
                buf.append(token)
                if start is None and s is not None:
                    start = s
                if e is not None:
                    end = e
        flush_small()

        return _merge_items_by_speaker(
            merged_small,
            field_text="text",
            field_speaker="speaker_id",
            field_start="start",
            field_end="end",
        )

    # 3) 타임라인 정보가 전혀 없고 전체 텍스트만 있을 때
    whole = getattr(resp, "text", None) or (resp.get("text") if isinstance(resp, dict) else None)
    if not whole:
        raise RuntimeError(f"STT 결과를 해석할 수 없습니다: {type(resp)}")
    return [{"speaker": "speech1", "text": whole.strip(), "start": None, "end": None}]
