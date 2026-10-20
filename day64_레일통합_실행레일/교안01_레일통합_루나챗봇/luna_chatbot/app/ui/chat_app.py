"""화면 층: 루나 팬 챗봇 한 페이지(Streamlit).

실행(프로젝트 폴더에서): uv run python -m streamlit run app/ui/chat_app.py
왼쪽에서 팬을 고르고 대화한다. 루나의 답 아래 '레일 판정 기록'을 펼치면 이번 턴의 판정, 경로, 검색 기록이 보인다.

비동기 처리: 판정 객체와 답변 모델은 처음 쓴 이벤트 루프에 묶인다. 화면이 다시 실행될 때마다 asyncio.run 으로
새 루프를 만들면 닫힌 루프의 객체를 다시 쓰게 되므로, 계속 살아 있는 루프 하나(ui/runner.py)에서
판정 객체를 만들고 매 턴을 실행한다. 체크포인터의 SQLite 연결은 그 루프 안에서 턴마다 열고 닫는다.
"""
from dataclasses import replace
from uuid import uuid4

import aiosqlite
import streamlit as st
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import AVATAR_PATH, CHECKPOINT_PATH, MAIN_EVENT_ID
from app.core.policies import contains_crisis_reply
from app.graph.builder import build_app
from app.graph.chat import build_chat_context, send_message, summarize_turn
from app.tools.fan_db import get_event, get_fan
from app.ui.components import (
    inject_css,
    render_blocked_card,
    render_guide_card,
    render_header,
    render_map_card,
    render_message,
    render_order_card,
    render_rail_trace,
    render_ticket_card,
)
from app.ui.runner import BackgroundLoop

# 로그인하지 않은 팬을 고르는 칸
NO_LOGIN = "로그인 안 함"

# 화면에서 고를 수 있는 팬(평가 케이스의 기준 팬)
LOGIN_IDS = ["F0001", "F0002", "F0003", "F0004", "F0006"]

# 대화가 비었을 때 보여 줄 예시 질문(질문과 그 질문이 쓰는 기능)
GUIDE_EXAMPLES = [
    "LUMI 1기 회원 혜택 알려 줘. (공지, 규정 검색)",
    "티켓은 공연 며칠 전까지 취소할 수 있어요? (규정 검색)",
    "내 티켓 좌석 어디예요? (로그인한 팬 본인 정보)",
    "「Lumi Night」 공연장 지도로 보여 줘. (공연장 주소와 지도)",
    "루나 오늘도 응원해! (일상 대화)",
]

# 경로 이름(라우터가 고른 경로, 로그인 안내, 입력 차단) -> 화면 글자
ROUTE_LABELS = {
    "refuse": "입력 레일이 막음(라우터 안 돎)",
    "out_of_scope": "업무 밖 질문(정해 둔 답)",
    "chitchat": "일상 대화(검색 없음)",
    "venue": "공연장 조회(검색 없음)",
    "my_ticket": "내 티켓 조회(검색 없음)",
    "my_order": "내 주문 조회(검색 없음)",
    "my_ticket_rule": "내 티켓 조회 후 규정 검색",
    "my_order_rule": "내 주문 조회 후 규정 검색",
    "login": "로그인 안내(조회 안 함)",
    "rag": "검색(RAG)",
}


# [보조 함수] 팬 선택 칸 글자
def fan_label(fan_id: str) -> str:
    """팬 선택 칸에 보일 '팬 id 닉네임 (등급)' 글자를 돌려준다. 로그인 안 함 칸은 그 글자 그대로다."""
    # 로그인 안 함 칸은 DB 에 없으므로 그대로 보여 준다
    if fan_id == NO_LOGIN:
        return NO_LOGIN

    # 팬 칸은 DB 에서 닉네임과 등급을 읽어 붙인다
    fan = get_fan(fan_id)
    return f"{fan_id} {fan['nickname']} ({fan['membership']})"


# [보조 함수] 공지 줄
def notice_html() -> str:
    """온라인 표시와 대표 공연(이름, 시작 시각, 공연장)을 담은 공지 줄 HTML 을 돌려준다."""
    event = get_event(MAIN_EVENT_ID)
    title = event["title"].replace("「", "").replace("」", "")
    # "2026-11-08 19:00:00" -> "2026.11.08 19:00"
    starts_at = event["starts_at"][:16].replace("-", ".")
    return (
        f'<div class="luna-notice"><span class="luna-online-dot"></span>'
        f'<b>{title}</b> {starts_at} {event["venue_name"]}</div>'
    )


# [보조 함수] 계속 살아 있는 루프
@st.cache_resource
def get_runner() -> BackgroundLoop:
    """화면이 다시 실행되어도 같은 이벤트 루프를 쓰도록 하나만 만들어 돌려준다."""
    return BackgroundLoop()


# [보조 함수] 실행 값을 루프 안에서 만들기
async def make_context():
    """판정 객체와 검색기를 살아 있는 루프 안에서 만들어 돌려준다(로그인한 팬은 턴마다 정한다)."""
    return build_chat_context()


# [보조 함수] 실행 값 한 번만 만들기
@st.cache_resource
def get_base_context():
    """판정 객체를 한 번만 만들어 돌려준다. 분류 모델을 매 턴 다시 읽지 않는다."""
    return get_runner().run(make_context())


# [보조 함수] 한 턴 실행
async def chat_turn(thread_id: str, text: str, context) -> dict:
    """체크포인터 연결을 이 턴 동안만 열어 팬 메시지 한 턴을 실행하고 턴 요약(summarize_turn 결과)을 돌려준다."""
    # 연결은 이 루프 안에서 열고 닫는다. 그래프는 연결에 묶이므로 턴마다 새로 컴파일한다(가벼운 일이다)
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(CHECKPOINT_PATH) as connection:
        app = build_app(AsyncSqliteSaver(connection))
        state = await send_message(app, thread_id, text, context)
    return summarize_turn(state)


# [보조 함수] 새 대화 시작
def start_new_conversation() -> None:
    """새 대화 ID 를 만들고 화면의 대화 기록을 비운다(돌려주는 값 없음)."""
    st.session_state["thread_id"] = str(uuid4())
    st.session_state["history"] = []


# [보조 함수] 레일 판정 기록 표
def rail_trace(summary: dict) -> dict:
    """턴 요약을 render_rail_trace 가 그리는 {단계 이름: 결과 dict 또는 글} 로 돌려준다(지나지 않은 단계는 넣지 않는다)."""
    trace = {}

    # 입력 레일: 막았으면 막은 흐름과 규칙 id 를 함께 보여 준다
    input_result = {"status": summary["input_status"]}
    if summary["route"] == "refuse":
        input_result["blocked_by"] = summary["blocked_by"]
        input_result["rule_id"] = summary["rule_id"]
    trace["입력 레일"] = input_result
    # 경로: 라우터가 고른 경로(로그인하지 않은 팬의 DB 질문은 로그인 안내)
    trace["경로(라우터)"] = ROUTE_LABELS.get(summary["route"], summary["route"])

    # 검색 기록은 검색 경로(규정 질문, 섞인 질문)를 지난 턴에만 있다
    if summary["search_query"] != "":
        trace["검색어"] = summary["search_query"]
        trace["검색 문서"] = ", ".join(summary["retrieved_ids"])
        removed = "뺀 절 없음"
        if len(summary["removed_doc_ids"]) > 0:
            removed = "뺀 절 " + ", ".join(summary["removed_doc_ids"])
        trace["검색 레일"] = removed

    # 출력 레일: 판정한 턴에만 보여 준다(업무 밖 질문의 정해 둔 답, 로그인 안내, 입력 차단 턴은 판정하지 않는다)
    if summary["output_status"] != "":
        output_result = {"status": summary["output_status"]}
        if summary["output_status"] == "blocked":
            output_result["blocked_by"] = summary["blocked_by"]
            output_result["rule_id"] = summary["rule_id"]
        trace["출력 레일"] = output_result
    return trace


# [보조 함수] 카드 그리기
def render_cards(cards: list) -> None:
    """턴 요약의 카드 목록을 종류(공연장, 티켓, 주문)에 맞는 화면 조각으로 그린다(돌려주는 값 없음)."""
    # 카드 종류마다 그리는 함수가 다르다. 막힘 카드(blocked)는 render_answer 가 따로 그린다
    for card in cards:
        if card["type"] == "venue":
            render_map_card(card["venue"])
        if card["type"] == "ticket":
            render_ticket_card(card["ticket"])
        if card["type"] == "order":
            render_order_card(card["order"])


# [보조 함수] 루나 답 하나 그리기
def render_answer(summary: dict) -> None:
    """루나의 답(막혔으면 막힘 카드), 조회 카드, 레일 판정 기록을 차례로 그린다(돌려주는 값 없음)."""
    # 막힌 턴은 말풍선 대신 차분한 막힘 카드 하나로 보여 준다(카드 안에 안내 문장과 규칙 id 가 있다)
    # 위기 안내(109, 112)가 든 답은 막혔어도 루나 말풍선으로 보여 준다. 위기 신호를 보낸 팬에게 차단 안내처럼 보이면 안 된다
    # 그때도 막은 흐름과 규칙 id 는 아래 레일 판정 기록에 남는다
    if summary["blocked_by"] != "" and not contains_crisis_reply(summary["answer"]):
        render_blocked_card(summary["rule_id"], summary["answer"])
    else:
        render_message("assistant", summary["answer"])
        render_cards(summary["cards"])
    render_rail_trace(rail_trace(summary))


# [화면] 한 페이지
def main() -> None:
    """팬 고르기, 머리, 지난 대화, 새 메시지 한 턴을 차례로 그린다(돌려주는 값 없음)."""
    st.set_page_config(page_title="루나 팬 챗봇", page_icon=str(AVATAR_PATH), layout="centered")
    inject_css()

    # 처음 열었을 때 대화 ID 와 기록을 만든다
    if "thread_id" not in st.session_state:
        start_new_conversation()
        st.session_state["fan_id"] = NO_LOGIN

    # 왼쪽 칸: 팬 고르기, 새 대화, 대화 ID
    fan_options = [NO_LOGIN] + LOGIN_IDS
    selected_fan = st.sidebar.selectbox("로그인한 팬", fan_options, format_func=fan_label)
    # 팬을 바꾸면 다른 팬의 대화가 섞이지 않게 새 대화로 시작한다
    if selected_fan != st.session_state["fan_id"]:
        st.session_state["fan_id"] = selected_fan
        start_new_conversation()
    if st.sidebar.button("새 대화"):
        start_new_conversation()
    st.sidebar.caption("대화 ID")
    st.sidebar.code(st.session_state["thread_id"], language=None)

    # 머리: 루나 얼굴과 이름, 로그인한 팬, 공지 줄
    login_fan_id = None
    profile = None
    if selected_fan != NO_LOGIN:
        login_fan_id = selected_fan
        profile = get_fan(selected_fan)
    render_header(profile)
    st.markdown(notice_html(), unsafe_allow_html=True)

    # 입력창은 어디서 불러도 화면 맨 아래에 붙는다. 먼저 받아 두어야 첫 메시지를 보낸 화면에서 안내 카드를 감출 수 있다
    text = st.chat_input("루나에게 메시지를 보내 보세요")

    # 대화가 비어 있고 아직 보낸 메시지가 없을 때만 무엇을 물어볼지 안내한다(대화가 시작되면 화면을 차지하지 않게 감춘다)
    if len(st.session_state["history"]) == 0 and not text:
        render_guide_card(
            "이렇게 물어보세요",
            "공지와 규정은 문서를 찾아 답하고, 내 티켓과 주문은 왼쪽에서 팬을 고르면 본인 것만 보여 줘요.",
            GUIDE_EXAMPLES,
            "막힐 만한 질문도 보내 보고, 답 아래 '레일 판정 기록'을 펼쳐 어느 레일이 막았는지 확인해 보세요.",
        )

    # 지난 대화: Streamlit 은 매번 처음부터 다시 그리므로 저장해 둔 기록을 다시 그린다
    for item in st.session_state["history"]:
        if item["role"] == "user":
            render_message("user", item["text"])
        else:
            render_answer(item["summary"])

    # 새 메시지: 팬 말풍선을 먼저 그리고, 살아 있는 루프에서 한 턴을 실행한 뒤 루나의 답을 그린다
    if text:
        render_message("user", text)
        context = replace(get_base_context(), fan_id=login_fan_id)
        with st.spinner("루나가 답을 준비하고 있어요"):
            turn_summary = get_runner().run(chat_turn(st.session_state["thread_id"], text, context))
        render_answer(turn_summary)

        # 다음에 화면을 다시 그릴 때 보이도록 이 턴을 기록에 남긴다
        st.session_state["history"].append({"role": "user", "text": text})
        st.session_state["history"].append({"role": "assistant", "summary": turn_summary})


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.ui.chat_app (화면 없이 안내만 출력한다)
    # 화면은 uv run python -m streamlit run app/ui/chat_app.py 로 띄운다. Streamlit 안에서 실행될 때만 페이지를 그린다
    from streamlit import runtime

    if runtime.exists():
        main()
    else:
        print("화면 실행: uv run python -m streamlit run app/ui/chat_app.py")
        print("고를 수 있는 팬:")
        for login_id in LOGIN_IDS:
            print(" ", fan_label(login_id))
        event = get_event(MAIN_EVENT_ID)
        print("대표 공연:", event["title"], event["starts_at"], event["venue_name"])
