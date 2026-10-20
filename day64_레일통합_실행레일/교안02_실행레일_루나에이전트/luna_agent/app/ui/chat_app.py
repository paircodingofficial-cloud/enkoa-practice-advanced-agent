"""화면 층: 루나 에이전트 채팅 한 페이지(Streamlit). 교안 01 챗봇과 같은 화면 조각(components.py)을 쓴다.

실행(프로젝트 폴더에서): uv run python -m streamlit run app/ui/chat_app.py

- 턴마다 도구 호출 표시와 실행 레일 판정, 레일 판정 기록을 보여 준다.
- 티켓, 주문, 공연장 지도, 팬아트, 막힘 카드를 도구 결과로 그린다.
- 취소, 환불이 승인을 기다리면 승인 카드를 띄우고, 누른 버튼으로 멈춘 실행을 이어 간다.

비동기 처리: 교안 01 과 같이 계속 살아 있는 루프 하나(ui/runner.py)에서 매 턴을 실행한다.
체크포인터의 SQLite 연결도 교안 01 과 같이 턴마다 열고 닫는다. 승인을 기다리며 멈춘 실행은 SQLite 파일에 저장돼 있어,
승인 버튼을 누른 뒤 새로 연 연결로도 같은 대화 ID 로 이어 갈 수 있다.
"""
import json
from uuid import uuid4

import aiosqlite
import streamlit as st
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import AVATAR_PATH, CHECKPOINT_PATH, DB_PATH, ROLE_TOOLS
from app.core.prompts import REJECT_MESSAGE
from app.core.schemas import AgentContext
from app.graph.builder import build_app
from app.graph.chat import is_human_rejection, rail_trace, resume_turn, send_message, summarize_turn, waits_for_approval
from app.guards.execution import remaining_fanarts
from app.tools.fan_db import get_fan
from app.ui.components import (
    badge_html,
    inject_css,
    render_approval_card,
    render_blocked_card,
    render_fanart_card,
    render_header,
    render_map_card,
    render_message,
    render_order_card,
    render_rail_trace,
    render_ticket_card,
)
from app.ui.runner import BackgroundLoop

# 화면에서 고를 수 있는 로그인 계정(평가 케이스의 기준 팬과 운영팀 한 명)
LOGIN_IDS = ["F0001", "F0002", "F0003", "F0004", "F0005", "F0006", "S0001"]

# 도구 결과 상태를 화면 표시 색과 글자로
# rejected: 도구가 실행됐지만 업무 규칙으로 거절함(예: 이미 예매된 좌석). 레일이 막은 것과 글자를 나눈다
# error 가운데 표시(rail)가 없는 것은 상담원 거절('거절함')이거나 도구 호출 오류('오류')라 render_tool_chips 가 따로 그린다
# pending 가운데 승인 도구가 아닌 것은 같은 메시지의 승인을 기다리는 호출이라 '대기' 로 그린다
EVENT_COLORS = {"success": "passed", "rejected": "modified", "error": "blocked", "pending": "info"}
EVENT_LABELS = {"success": "실행", "rejected": "거절", "error": "막음", "pending": "승인 대기"}

# 승인 카드 제목. 승인은 상담원이 한다. 이 실습 화면에서는 로그인한 내가 상담원 역할로 버튼을 누른다
APPROVAL_TITLE = "상담원 승인이 필요해요(실습에서는 내가 상담원 역할)"


# [보조 함수] 계속 살아 있는 루프
@st.cache_resource
def get_runner() -> BackgroundLoop:
    """화면이 다시 실행되어도 같은 이벤트 루프를 쓰도록 하나만 만들어 돌려준다."""
    return BackgroundLoop()


# [보조 함수] 한 턴 실행
async def chat_turn(thread_id: str, text: str, context: AgentContext) -> dict:
    """체크포인터 연결을 이 턴 동안만 열어 팬 메시지 한 턴을 실행하고 턴 요약을 돌려준다."""
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(CHECKPOINT_PATH) as connection:
        app = build_app(AsyncSqliteSaver(connection))
        result = await send_message(app, thread_id, text, context)
    return summarize_turn(result)


# [보조 함수] 멈춘 승인 이어 가기
async def resume_chat_turn(thread_id: str, decisions: list, context: AgentContext) -> dict:
    """체크포인터 연결을 다시 열어 승인을 기다리던 실행을 결정 목록으로 이어 가고 턴 요약을 돌려준다."""
    async with aiosqlite.connect(CHECKPOINT_PATH) as connection:
        app = build_app(AsyncSqliteSaver(connection))
        result = await resume_turn(app, thread_id, decisions, context)
    return summarize_turn(result)


# [화면] 도구 호출 표시
def render_tool_chips(events: list) -> None:
    """이번 턴의 도구 호출을 이름과 실행 레일 결과 표시로 한 줄에 그린다."""
    chips = []
    for event in events:
        # 기본: 상태별 글자와 색
        label = EVENT_LABELS[event["status"]]
        color = EVENT_COLORS[event["status"]]
        # 규정 검색 결과에서 숨은 지시를 뺐음
        if event["rail"] == "check_tool_result":
            label = "절 뺌"
        # 표시 없는 오류: 도구 호출 오류로 그리고, 사람 거절이면 글자만 바꾼다
        if event["status"] == "error" and event["rail"] == "":
            label = "오류"
            color = "info"
        if is_human_rejection(event):
            label = "거절함"
        # 승인 도구가 아닌데 결과가 없음: 같은 메시지의 승인을 기다리는 호출
        if event["status"] == "pending" and not waits_for_approval(event):
            label = "대기"
        chips.append(f'<span class="luna-chip muted">{event["name"]}</span>{badge_html(color, label)}')
    if chips:
        st.markdown('<div class="luna-chip-row">' + " ".join(chips) + "</div>", unsafe_allow_html=True)


# [화면] 도구 결과 카드
def render_tool_cards(events: list) -> None:
    """실행된 도구 결과로 티켓, 주문, 공연장 지도, 팬아트 카드를 그리고, 실행 레일이 막은 호출은 막힘 카드로 그린다."""
    for event in events:
        # 팬아트는 검사에서 막혀도 검사 결과를 보여 준다
        if event["name"] == "create_fanart" and event["artifact"] is not None and "verdicts" in event["artifact"]:
            artifact = event["artifact"]
            render_fanart_card(artifact["path"], artifact["verdicts"], artifact["remaining"])
            continue
        # 실행 레일이 막은 호출: 막힘 카드
        if event["status"] == "error" and event["rail"] != "":
            render_blocked_card(event["rule_id"], event["content"])
            continue
        # 실행되지 않은 호출(거절, 대기, 오류): 그릴 결과가 없다
        if event["status"] != "success":
            continue

        # 조회 도구의 결과는 JSON 글이다. 목록은 {"tickets": [...]}, {"orders": [...]} 로 와서 비어 있어도 읽을 수 있다
        # 도구가 업무 규칙으로 거절한 결과(rejected)는 위에서 건너뛰어 카드를 그리지 않는다
        if event["name"] == "get_my_tickets":
            for ticket in json.loads(event["content"])["tickets"]:
                render_ticket_card(ticket)
        if event["name"] == "get_my_orders":
            for order in json.loads(event["content"])["orders"]:
                render_order_card(order)
        if event["name"] == "get_event_venue":
            render_map_card(json.loads(event["content"]))


# [화면] 턴 하나
def render_turn(turn: dict) -> None:
    """팬 메시지, 도구 표시, 카드, 루나 답, 레일 판정 기록을 차례로 그린다."""
    summary = turn["summary"]
    render_message("user", turn["question"])
    render_tool_chips(summary["tool_events"])
    render_tool_cards(summary["tool_events"])

    # 입력, 출력 레일이 막았으면 그 레일의 규칙 id 로 막힘 카드를, 아니면 루나 말풍선으로 답을 보여 준다
    # summary["rule_id"] 는 쓰지 않는다. 같은 턴에 실행 레일이 먼저 막은 도구가 있으면 그 규칙 id 가 들어 있다
    blocked_verdict = {}
    if summary["input_verdict"] and summary["input_verdict"]["status"] == "blocked":
        blocked_verdict = summary["input_verdict"]
    if summary["output_verdict"] and summary["output_verdict"]["status"] == "blocked":
        blocked_verdict = summary["output_verdict"]
    if blocked_verdict:
        render_blocked_card(blocked_verdict["rule_id"], summary["answer"])
    elif summary["answer"]:
        render_message("assistant", summary["answer"])
    render_rail_trace(rail_trace(summary))


# [화면] 승인 카드와 재개
def handle_approval(context: AgentContext) -> None:
    """마지막 턴이 승인을 기다리면 승인 카드를 그리고, 모든 작업의 결정이 모이면 멈춘 실행을 이어 간다."""
    thread_id = st.session_state.thread_id
    last = st.session_state.turns[-1]
    pending = last["summary"]["pending"]
    for index, action in enumerate(pending):
        details = {"작업": action["name"], "대상": json.dumps(action["args"], ensure_ascii=False), "내용": action["description"]}
        choice = render_approval_card(APPROVAL_TITLE, details, key=f"{thread_id}_{len(st.session_state.turns)}_{index}")
        # 버튼을 누른 작업만 결정을 적는다(누르지 않았으면 None)
        if choice is not None:
            st.session_state.decisions[index] = choice

    # 작업마다 결정이 다 모이면 같은 대화 id 로 이어 간다(결정 순서 = 작업 순서)
    # 아직 결정하지 않은 작업이 있으면 다음 버튼을 기다린다
    if len(st.session_state.decisions) < len(pending):
        return
    decisions = []
    for index in range(len(pending)):
        if st.session_state.decisions[index] == "approve":
            decisions.append({"type": "approve"})
        # 거절 버튼: 거절 문장이 도구 결과로 모델에게 간다
        else:
            decisions.append({"type": "reject", "message": REJECT_MESSAGE})
    with st.spinner("이어서 처리하는 중이에요"):
        last["summary"] = get_runner().run(resume_chat_turn(thread_id, decisions, context))
    st.session_state.decisions = {}
    st.rerun()


# [보조 함수] 새 대화 시작
def reset_chat() -> None:
    """새 대화 id 를 만들고 화면의 턴 기록과 승인 결정을 비운다."""
    st.session_state.thread_id = str(uuid4())
    st.session_state.turns = []
    st.session_state.decisions = {}


# [화면] 채팅 페이지
def main() -> None:
    """채팅 페이지 한 장을 그린다. Streamlit 이 버튼을 누를 때마다 처음부터 다시 부른다."""
    st.set_page_config(page_title="루나 팬 서비스 에이전트", page_icon=str(AVATAR_PATH), layout="centered")
    inject_css()
    # 처음 연 페이지: 새 대화로 시작한다
    if "thread_id" not in st.session_state:
        reset_chat()

    # 로그인: 계정을 바꾸면 새 대화로 시작한다. 역할은 DB 의 로그인 정보로 정한다
    with st.sidebar:
        login_id = st.selectbox("로그인 계정", LOGIN_IDS, on_change=reset_chat)
        fan = get_fan(login_id)
        context = AgentContext(fan_id=fan["fan_id"], role=fan["role"], db_path=DB_PATH)
        st.caption(f"역할: {fan['role']} / 오늘 남은 팬아트: {remaining_fanarts(context)}회")
        st.caption("모델에게 보이는 도구: " + ", ".join(ROLE_TOOLS[fan["role"]]))
        if st.button("새 대화"):
            reset_chat()
            st.rerun()
        st.caption(f"대화 id: {st.session_state.thread_id}")

    render_header(fan)
    for past_turn in st.session_state.turns:
        render_turn(past_turn)

    # 승인을 기다리는 턴이 있으면 입력창 대신 승인 카드를 보여 준다
    if st.session_state.turns and st.session_state.turns[-1]["summary"]["pending"]:
        handle_approval(context)
    else:
        question = st.chat_input("루나에게 물어보세요. 예: 내 티켓 좌석 알려 줘")
        # 메시지를 보낸 실행에서만 한 턴을 돌린다
        if question:
            with st.spinner("루나가 확인하는 중이에요"):
                summary = get_runner().run(chat_turn(st.session_state.thread_id, question, context))
            st.session_state.turns.append({"question": question, "summary": summary})
            st.rerun()


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.ui.chat_app (화면 없이 안내만 출력한다)
    # 화면은 uv run python -m streamlit run app/ui/chat_app.py 로 띄운다. Streamlit 안에서 실행될 때만 페이지를 그린다
    from streamlit import runtime

    if runtime.exists():
        main()
    else:
        print("화면 실행: uv run python -m streamlit run app/ui/chat_app.py")
        print("로그인 계정 후보:", LOGIN_IDS)
        print("역할별 도구:", ROLE_TOOLS)
