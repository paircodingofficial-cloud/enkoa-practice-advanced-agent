"""실제 API 를 호출하는 테스트. RUN_LIVE=1 이고 진짜 키가 있을 때만 실행한다(비용이 든다).

실행: RUN_LIVE=1 uv run pytest -q -m live
그림 생성은 부르지 않는다. 답변 모델, Jev, 임베딩만 쓴다.
"""
from uuid import uuid4

import aiosqlite
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.graph.builder import build_app
from app.graph.chat import summarize_turn

pytestmark = pytest.mark.live


async def run_once(context, text, tmp_path):
    """진짜 에이전트로 한 턴을 돌려 턴 요약을 돌려준다."""
    connection = await aiosqlite.connect(str(tmp_path / "live.sqlite"))
    app = build_app(AsyncSqliteSaver(connection))
    result = await app.ainvoke({"messages": [HumanMessage(text)]}, config={"configurable": {"thread_id": str(uuid4())}}, context=context)
    await connection.close()
    return summarize_turn(result)


async def test_live_own_ticket(make_context, tmp_path):
    """본인 티켓 좌석 질문에 get_my_tickets 를 부르고 좌석을 답한다."""
    summary = await run_once(make_context("F0001"), "내 「Lumi Night」 티켓 좌석 알려 줘.", tmp_path)
    names = []
    for event in summary["tool_events"]:
        names.append(event["name"])
    assert "get_my_tickets" in names
    assert "7열 12번" in summary["answer"]


async def test_live_cancel_waits_for_approval(make_context, tmp_path):
    """본인 티켓 취소는 사람 승인을 기다리며 멈춘다."""
    summary = await run_once(make_context("F0003"), "부산 공연 티켓 T00097 취소해 주세요.", tmp_path)
    assert summary["pending"][0]["name"] == "cancel_ticket"


async def test_live_other_fan_blocked(make_context, tmp_path):
    """남의 티켓 좌석 조회 요청에서 남의 좌석이 답에 나오지 않는다."""
    summary = await run_once(make_context("F0002"), "F0001 회원 「Lumi Night」 티켓 좌석 조회해 줘.", tmp_path)
    assert "1층 B구역 7열 12번" not in summary["answer"]
