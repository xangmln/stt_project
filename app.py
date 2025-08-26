import json
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

st.set_page_config(page_title="상담 평가 뷰어", layout="wide")

SAMPLE_JSON = r'''
{
  "keyword": [
    "잘못된 전화",
    "번호 도용",
    "상담 불가"
  ],
  "summary": "본 통화는 고객이 중고차 상담을 원하지 않았으며, 전화 번호가 도용된 것으로 확인되어 실제 상담이 이루어지지 않았습니다. 상담원은 상황을 인지한 후 신속하게 통화를 종료했습니다.",
  "is_valid": "False",
  "feedback": "본 통화는 잘못 걸려온 전화로 인해 실제 상담이 진행되지 않아 상담원의 역량을 평가하기 어렵습니다. 상담원은 전화를 받으며 기본적인 인사를 했으나, 이후 고객의 통화 의사가 없음을 확인하고 신속하게 상황을 정리했습니다. 향후 유사한 상황 발생 시에도 매뉴얼에 따라 적절하게 대응하는 것이 중요합니다.",
  "agent_id": "smsamlee",
  "conversation_list": [
    {
      "text": "여보세요",
      "turn": 1,
      "speaker_role": "customer"
    },
    {
      "text": "네, 안녕하세요 중고차입니다.",
      "turn": 2,
      "speaker_role": "agent"
    },
    {
      "text": "음, 그런 적 없어요. 누가 도용한 거 같아요.",
      "turn": 3,
      "speaker_role": "customer"
    },
    {
      "text": "아, 고객님이 남기신 거 아니신 거죠?",
      "turn": 4,
      "speaker_role": "agent"
    },
    {
      "text": "예.",
      "turn": 5,
      "speaker_role": "customer"
    },
    {
      "text": "네, 알겠습니다.",
      "turn": 6,
      "speaker_role": "agent"
    }
  ],
  "criteria": {
    "문의 차량 확인": {
      "evidence": [],
      "description": "잘못 걸려온 전화로 인해 문의 차량 확인이 이루어지지 않았습니다.",
      "improvement": "해당 없음",
      "score": 0
    },
    "용도나 구매시기": {
      "evidence": [],
      "description": "잘못 걸려온 전화로 인해 고객의 용도나 구매 시기에 대한 정보 확인이 이루어지지 않았습니다.",
      "score": 0,
      "improvement": "해당 없음"
    },
    "적극적 세일즈": {
      "description": "잘못 걸려온 전화로 인해 상담 진행 자체가 불가능하여 적극적인 세일즈를 평가할 수 없습니다.",
      "score": 0
    },
    "지역": {
      "evidence": [],
      "description": "잘못 걸려온 전화로 인해 고객의 지역에 대한 정보 확인이 이루어지지 않았습니다.",
      "score": 0,
      "improvement": "해당 없음"
    },
    "방문일시": {
      "evidence": [],
      "description": "잘못 걸려온 전화로 인해 방문 일시에 대한 논의가 이루어지지 않았습니다.",
      "improvement": "해당 없음",
      "score": 0
    },
    "인사": {
      "evidence": [
        "네, 안녕하세요 중고차입니다."
      ],
      "description": "상담원이 전화를 받으며 기본적인 인사를 했으나, 잘못 걸려온 전화로 인해 추가적인 상담 진행이 불가했습니다.",
      "score": 50,
      "improvement": "해당 없음"
    },
    "결제 방법": {
      "evidence": [],
      "description": "잘못 걸려온 전화로 인해 결제 방법에 대한 논의가 이루어지지 않았습니다.",
      "improvement": "해당 없음",
      "score": 0
    },
    "고객 물음에 대한 적극 응대": {
      "evidence": [],
      "description": "잘못 걸려온 전화로 인해 고객의 구체적인 물음이 없었으므로 응대 여부를 평가할 수 없습니다.",
      "score": 0,
      "improvement": "해당 없음"
    },
    "차량에 대한 안내": {
      "evidence": [],
      "description": "잘못 걸려온 전화로 인해 차량에 대한 안내가 이루어지지 않았습니다.",
      "improvement": "해당 없음",
      "score": 0
    }
  },
  "overall_score": 0
}
'''

# ---------------------- 유틸 ----------------------
def load_json_from_textarea(text: str) -> Dict[str, Any]:
    text = text.strip()
    if not text:
        return {}
    return json.loads(text)


def gather_all_evidence(criteria: Dict[str, Any]) -> List[str]:
    evid = []
    for _, v in criteria.items():
        ev = v.get("evidence") or []
        if isinstance(ev, list):
            evid.extend(ev)
    return list(dict.fromkeys(evid))  # 중복 제거, 순서 유지


def badge(text: str) -> str:
    return f"""
    <span style="
        display:inline-block; padding:4px 8px; margin:2px;
        border-radius:999px; background:#eef2ff; border:1px solid #c7d2fe;
        font-size:12px; color:#3730a3;">{text}</span>
    """


def status_chip(ok: bool) -> str:
    color = "#059669" if ok else "#dc2626"
    bg = "#ecfdf5" if ok else "#fef2f2"
    txt = "Valid" if ok else "Invalid"
    return f"""
    <span style="display:inline-block;padding:4px 10px;border-radius:8px;
                 background:{bg}; color:{color}; border:1px solid {color}; font-weight:600;">
      {txt}
    </span>
    """


# ---------------------- 사이드바: 입력 ----------------------
st.sidebar.header("입력 데이터")
mode = st.sidebar.radio("데이터 소스", ["업로드", "붙여넣기", "샘플 불러오기"], index=2)

raw_json = ""
if mode == "업로드":
    file = st.sidebar.file_uploader("JSON 파일 업로드", type=["json"])
    if file:
        raw_json = file.read().decode("utf-8", errors="ignore")
elif mode == "붙여넣기":
    raw_json = st.sidebar.text_area("JSON 붙여넣기", height=300, placeholder="{ ... }")
else:
    raw_json = SAMPLE_JSON

data = {}
error = None
try:
    data = load_json_from_textarea(raw_json)
except Exception as e:
    error = str(e)

if error:
    st.error(f"JSON 파싱 오류: {error}")
    st.stop()

if not data:
    st.info("좌측에서 JSON을 업로드하거나 붙여넣어 주세요.")
    st.stop()

# ---------------------- 상단 헤더 ----------------------
st.title("📊 상담 평가 뷰어")

col1, col2, col3, col4 = st.columns([1, 2, 2, 3])
with col1:
    overall = int(data.get("overall_score", 0) or 0)
    st.metric("종합 점수", f"{overall} / 100")
    st.progress(min(max(overall, 0), 100) / 100)
with col2:
    st.markdown("**에이전트 ID**")
    st.code(str(data.get("agent_id", "-")), language="text")
with col3:
    st.markdown("**유효성**")
    valid_raw = str(data.get("is_valid", "")).strip().lower()
    is_valid = valid_raw in ("true", "1", "yes", "y")
    st.markdown(status_chip(is_valid), unsafe_allow_html=True)
with col4:
    st.markdown("**키워드**")
    kws = data.get("keyword") or []
    if isinstance(kws, list):
        st.markdown("".join([badge(k) for k in kws]), unsafe_allow_html=True)

# ---------------------- 요약/피드백 ----------------------
with st.expander("🧾 요약", expanded=True):
    st.write(data.get("summary", ""))

with st.expander("💬 피드백", expanded=False):
    st.write(data.get("feedback", ""))

# ---------------------- Criteria ----------------------
st.subheader("📌 평가 기준 (Criteria)")
criteria: Dict[str, Any] = data.get("criteria") or {}

if not criteria:
    st.info("criteria 데이터가 없습니다.")
else:
    crit_names = list(criteria.keys())
    # 2열 그리드로 깔끔하게
    cols = st.columns(2)
    for i, name in enumerate(crit_names):
        col = cols[i % 2]
        with col:
            c = criteria[name] or {}
            score = c.get("score")
            desc = c.get("description", "")
            improvement = c.get("improvement", "")
            evid = c.get("evidence", []) or []

            with st.container(border=True):
                st.markdown(f"### {name}")
                if score is not None:
                    st.write(f"**점수:** {score}")
                    st.progress(min(max(int(score), 0), 100) / 100)
                if desc:
                    st.markdown(f"**설명**")
                    st.write(desc)
                if improvement:
                    st.markdown(f"**개선점**")
                    st.info(improvement)
                if evid:
                    st.markdown("**증거(Evidence)**")
                    for e in evid:
                        st.markdown(f"- {e}")

# ---------------------- 대화 내역 (챗봇 스타일) ----------------------
st.subheader("💬 대화 내역 (Chat View)")

conv = data.get("conversation_list") or []
if not conv:
    st.info("conversation_list 데이터가 없습니다.")
else:
    # DataFrame으로 정리
    df = pd.DataFrame(conv)

    # 스피커/검색 필터
    left, mid, right = st.columns([2, 2, 1])
    with left:
        speakers = sorted(df["speaker_role"].dropna().unique().tolist())
        selected_speakers = st.multiselect("발화자 필터", speakers, default=speakers)
    with mid:
        query = st.text_input("대화 검색(텍스트 포함)")
    with right:
        sort_turn = st.toggle("턴 기준 정렬", value=True)

    # 증거 문장 수집
    criteria: Dict[str, Any] = data.get("criteria") or {}
    def gather_all_evidence(criteria: Dict[str, Any]) -> List[str]:
        evid = []
        for _, v in criteria.items():
            ev = v.get("evidence") or []
            if isinstance(ev, list):
                evid.extend(ev)
        # 중복 제거, 순서 유지
        return list(dict.fromkeys(evid))

    all_evidence = gather_all_evidence(criteria)

    # 필터 적용
    view = df.copy()
    if selected_speakers:
        view = view[view["speaker_role"].isin(selected_speakers)]
    if query:
        q = query.strip().lower()
        view = view[view["text"].str.lower().str.contains(q, na=False)]
    if sort_turn and "turn" in view.columns:
        view = view.sort_values("turn", ascending=True)

    # 역할 매핑 (Streamlit chat_message는 'user'/'assistant' 권장)
    role_map = {
        "customer": "user",
        "agent": "assistant",
    }
    # 아바타 이모지(원하면 바꿔도 됩니다)
    avatar_map = {
        "user": "🧑",        # customer
        "assistant": "🤖",   # agent
    }

    # 강조 스타일: 증거 문장인 경우 말풍선 아래 뱃지로 표기
    def render_message(row: pd.Series):
        role = role_map.get(str(row.get("speaker_role", "")).lower(), "user")
        text = str(row.get("text", ""))
        is_evi = text in all_evidence

        with st.chat_message(role, avatar=avatar_map.get(role, None)):
            # 말풍선 본문
            st.write(text)

            # 메타(턴 번호)
            turn_no = row.get("turn", None)
            if turn_no is not None:
                st.caption(f"turn: {turn_no}")

            # 증거 표시
            if is_evi:
                st.markdown(
                    '<span style="display:inline-block;padding:2px 8px;'
                    'border-radius:999px;border:1px solid #16a34a;'
                    'background:#ecfdf5;color:#166534;font-size:12px;'
                    'font-weight:600;">EVIDENCE</span>',
                    unsafe_allow_html=True
                )

    # 실제 렌더링
    for _, row in view.iterrows():
        render_message(row)

    # 표보기 토글(필요하면 원래 테이블도 확인할 수 있게)
    if st.toggle("원본 테이블 보기", value=False):
        st.dataframe(
            view[["turn", "speaker_role", "text"]],
            use_container_width=True,
            hide_index=True
        )
# -------------------------------------------------------
st.caption("Tip: 좌측에서 '붙여넣기' 또는 '업로드'를 선택해 실제 데이터를 바로 볼 수 있습니다.")