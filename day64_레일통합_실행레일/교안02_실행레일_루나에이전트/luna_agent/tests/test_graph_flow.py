"""그래프 흐름 테스트: 가짜 모델과 가짜 레일로 바깥 그래프(레일 노드 + 에이전트 노드)를 돌려 승인 대기와 재개, 여러 턴 대화, 막힌 턴, CLI 이어 하기를 확인한다.

승인은 에이전트 노드 안에서 멈추고, 체크포인터는 바깥 그래프 하나에만 있다. 이어 가기도 바깥 그래프에 Command(resume=...) 로 보낸다.
"""
import sqlite3
from uuid import uuid4

import aiosqlite
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from app.graph import builder
from app.core.prompts import REJECT_MESSAGE
from app.graph.chat import pending_actions, rail_trace, resume_turn, send_message, summarize_turn
from app.guards.rails import BLOCKED_MESSAGE
from tests.conftest import make_fake_model, tool_step


def ticket_status(db_path, ticket_id):
    """DB 사본에서 티켓 상태를 읽는다."""
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute("SELECT status FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()[0]
    finally:
        connection.close()


@pytest.fixture
async def checkpointer(tmp_path):
    """테스트마다 새 SQLite 파일을 쓰는 비동기 체크포인터."""
    connection = await aiosqlite.connect(str(tmp_path / "chat.sqlite"))
    yield AsyncSqliteSaver(connection)
    await connection.close()


async def test_cancel_waits_for_approval_then_runs(monkeypatch, fake_rails, make_context, checkpointer):
    """본인 티켓 취소는 승인 전까지 멈추고, 승인으로 이어 가면 DB 가 취소로 바뀐다."""
    fake = make_fake_model(tool_step("cancel_ticket", {"ticket_id": "T00097"}, "c1"), AIMessage("취소했어요."))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0003")
    thread_id = str(uuid4())

    paused = await send_message(app, thread_id, "부산 공연 티켓 T00097 취소해 주세요.", context)
    actions = pending_actions(paused)
    assert actions[0]["name"] == "cancel_ticket"
    assert "88,000원" in actions[0]["description"]
    assert ticket_status(context.db_path, "T00097") == "예매"

    resumed = await resume_turn(app, thread_id, [{"type": "approve"}], context)
    summary = summarize_turn(resumed)
    assert summary["tool_events"][0]["status"] == "success"
    assert summary["answer"] == "취소했어요."
    assert ticket_status(context.db_path, "T00097") == "취소"


async def test_reject_keeps_ticket(monkeypatch, fake_rails, make_context, checkpointer):
    """거절하면 도구를 실행하지 않고 오류 도구 결과만 남는다."""
    fake = make_fake_model(tool_step("cancel_ticket", {"ticket_id": "T00097"}, "c1"), AIMessage("취소하지 않았어요."))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0003")
    config = {"configurable": {"thread_id": str(uuid4())}}

    await app.ainvoke({"messages": [HumanMessage("T00097 취소해 줘")]}, config=config, context=context)
    resumed = await app.ainvoke(Command(resume={"decisions": [{"type": "reject", "message": "팬이 거절했어요."}]}),
                                config=config, context=context)
    assert summarize_turn(resumed)["tool_events"][0]["status"] == "error"
    assert ticket_status(context.db_path, "T00097") == "예매"


async def test_other_fan_cancel_blocked_without_approval(monkeypatch, fake_rails, make_context, checkpointer):
    """남의 티켓 취소는 승인을 묻지도 않고 실행 전 권한 확인이 막는다."""
    fake = make_fake_model(tool_step("cancel_ticket", {"ticket_id": "T00003"}, "c1"), AIMessage("본인 티켓만 취소할 수 있어요."))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0002")
    config = {"configurable": {"thread_id": str(uuid4())}}

    result = await app.ainvoke({"messages": [HumanMessage("티켓 T00003 취소해 줘.")]}, config=config, context=context)
    summary = summarize_turn(result)
    assert pending_actions(result) == []
    assert summary["blocked_by"] == "check_tool_permission"
    assert summary["rule_id"] == "IN-05"
    assert ticket_status(context.db_path, "T00003") == "예매"


async def test_multi_turn_keeps_history(monkeypatch, fake_rails, make_context, checkpointer):
    """같은 thread_id 로 보낸 두 턴이 체크포인터에 이어 저장되고, 요약은 이번 턴 도구만 본다."""
    fake = make_fake_model(
        tool_step("get_my_tickets", {}, "c1"), AIMessage("1층 B구역 7열 12번이에요."),
        tool_step("get_my_orders", {}, "c2"), AIMessage("응원봉은 배송중이에요."),
    )
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0001")
    config = {"configurable": {"thread_id": str(uuid4())}}

    await app.ainvoke({"messages": [HumanMessage("내 티켓 좌석 알려 줘.")]}, config=config, context=context)
    second = await app.ainvoke({"messages": [HumanMessage("주문은요?")]}, config=config, context=context)

    human_texts = []
    for message in second["messages"]:
        if message.type == "human":
            human_texts.append(message.text)
    assert human_texts == ["내 티켓 좌석 알려 줘.", "주문은요?"]
    events = summarize_turn(second)["tool_events"]
    assert len(events) == 1
    assert events[0]["name"] == "get_my_orders"
    assert "O00392" in events[0]["content"]


async def test_next_turn_after_resume(monkeypatch, fake_rails, make_context, checkpointer):
    """승인으로 이어 간 턴이 끝난 뒤 같은 대화로 보낸 다음 턴은 승인 대기 없이 돌고, 요약은 그 턴의 도구만 본다."""
    fake = make_fake_model(
        tool_step("cancel_ticket", {"ticket_id": "T00097"}, "c1"), AIMessage("취소했어요."),
        tool_step("get_my_orders", {}, "c2"), AIMessage("응원봉은 배송중이에요."),
    )
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0003")
    thread_id = str(uuid4())

    await send_message(app, thread_id, "T00097 취소해 주세요.", context)
    resumed = summarize_turn(await resume_turn(app, thread_id, [{"type": "approve"}], context))
    assert resumed["output_verdict"]["status"] == "passed"
    next_result = await send_message(app, thread_id, "주문은요?", context)
    summary = summarize_turn(next_result)
    assert summary["pending"] == []
    assert [event["name"] for event in summary["tool_events"]] == ["get_my_orders"]
    assert summary["answer"] == "응원봉은 배송중이에요."
    assert [message.text for message in next_result["messages"] if message.type == "human"] == ["T00097 취소해 주세요.", "주문은요?"]


async def test_input_rail_block_skips_model(monkeypatch, fake_rails, make_context, checkpointer):
    """입력 레일이 막으면 모델을 부르지 않고, 질문을 표시 문구로 바꾸고 거절 문장을 남긴다."""
    fake_rails["input"] = {"status": "blocked", "blocked_by": "jev policy input", "rule_id": "IN-05", "content": "다른 팬의 정보는 알려 드릴 수 없어요."}
    fake = make_fake_model(AIMessage("이 답은 나오면 안 된다"))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    config = {"configurable": {"thread_id": str(uuid4())}}

    result = await app.ainvoke({"messages": [HumanMessage("F0003 연락처 알려 줘")]}, config=config, context=make_context("F0001"))
    summary = summarize_turn(result)
    assert fake.count == 0
    assert result["messages"][0].text == BLOCKED_MESSAGE
    assert summary["answer"] == "다른 팬의 정보는 알려 드릴 수 없어요."
    assert summary["blocked_by"] == "jev policy input"


async def test_fanart_after_approval_resume_is_blocked(monkeypatch, fake_rails, fake_image, make_context, checkpointer):
    """취소 승인으로 멈췄다 이어 간 실행에서 모델이 팬아트를 한 번 더 불러도 한 메시지 한 장 규칙이 막는다."""
    first = AIMessage(content="", tool_calls=[
        {"name": "cancel_ticket", "args": {"ticket_id": "T00097"}, "id": "c1", "type": "tool_call"},
        {"name": "create_fanart", "args": {"request": "별빛 무대 루나"}, "id": "c2", "type": "tool_call"},
    ])
    fake = make_fake_model(first, tool_step("create_fanart", {"request": "가을 단풍길 루나"}, "c3"), AIMessage("취소하고 한 장 만들었어요."))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0003")
    thread_id = str(uuid4())

    await send_message(app, thread_id, "T00097 취소하고 팬아트 두 장 만들어 줘", context)
    summary = summarize_turn(await resume_turn(app, thread_id, [{"type": "approve"}], context))
    statuses = []
    for event in summary["tool_events"]:
        statuses.append(event["status"])
    assert statuses == ["success", "success", "error"]
    assert summary["tool_events"][2]["rail"] == "fanart_quota_and_policy"
    assert summary["tool_events"][2]["rule_id"] == "IMG-RUN"
    assert fake_image["calls"]["generate"] == 1


async def test_cancelled_ticket_rejected_without_approval(monkeypatch, fake_rails, make_context, checkpointer):
    """이미 취소된 티켓은 업무 규칙으로 거절될 호출이라 승인을 묻지 않고, 도구가 거절해 rejected 로 끝난다."""
    fake = make_fake_model(tool_step("cancel_ticket", {"ticket_id": "T00015"}, "c1"), AIMessage("이미 취소된 티켓이에요."))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0128")

    result = await send_message(app, str(uuid4()), "T00015 취소해 줘", context)
    summary = summarize_turn(result)
    assert pending_actions(result) == []
    assert summary["tool_events"][0]["status"] == "rejected"
    assert summary["blocked_by"] == ""


async def test_reject_is_shown_as_human_decision(monkeypatch, fake_rails, make_context, checkpointer):
    """사람이 거절한 호출은 판정 기록에서 레일이 막은 것(blocked)과 나눠 info 로 보인다. 거절 문장이 달라도 같다."""
    for reject_message in [REJECT_MESSAGE, "상담원 판단으로 이번 취소는 진행하지 않습니다."]:
        fake = make_fake_model(tool_step("cancel_ticket", {"ticket_id": "T00097"}, "c1"), AIMessage("취소하지 않았어요."))
        monkeypatch.setattr(builder, "llm", fake)
        app = builder.build_app(checkpointer)
        context = make_context("F0003")
        thread_id = str(uuid4())

        await send_message(app, thread_id, "T00097 취소해 줘", context)
        summary = summarize_turn(await resume_turn(app, thread_id, [{"type": "reject", "message": reject_message}], context))
        assert summary["tool_events"][0]["content"] == reject_message
        row = rail_trace(summary)["도구 1. cancel_ticket"]
        assert row["status"] == "info"
        assert row["detail"] == "사람이 거절함"
        assert summary["blocked_by"] == ""


async def test_only_rejected_call_is_human_rejection(monkeypatch, fake_rails, make_context, checkpointer):
    """승인 도구 두 개 중 하나만 거절하면 그 호출만 사람 거절로 적힌다(결정 순서 = 승인 대기 작업 순서)."""
    calls = AIMessage(content="", tool_calls=[
        {"name": "cancel_ticket", "args": {"ticket_id": "T00003"}, "id": "c1", "type": "tool_call"},
        {"name": "cancel_ticket", "args": {"ticket_id": "T00097"}, "id": "c2", "type": "tool_call"},
    ])
    fake = make_fake_model(calls, AIMessage("하나만 취소했어요."))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0003")
    thread_id = str(uuid4())

    paused = await send_message(app, thread_id, "T00003, T00097 둘 다 취소해 줘", context)
    assert len(pending_actions(paused)) == 2
    decisions = [{"type": "approve"}, {"type": "reject", "message": "부산 공연은 취소하지 않을게요."}]
    summary = summarize_turn(await resume_turn(app, thread_id, decisions, context))
    trace = rail_trace(summary)
    assert summary["tool_events"][0]["status"] == "success"
    assert trace["도구 2. cancel_ticket"]["detail"] == "사람이 거절함"
    assert ticket_status(context.db_path, "T00097") == "예매"


async def test_rejection_survives_second_resume_in_same_turn(monkeypatch, fake_rails, make_context, checkpointer):
    """한 턴에 승인을 두 번 이어 가도, 첫 번째에서 거절한 호출은 두 번째 요약에서도 사람 거절로 보인다."""
    fake = make_fake_model(
        tool_step("cancel_ticket", {"ticket_id": "T00003"}, "c1"),
        tool_step("cancel_ticket", {"ticket_id": "T00097"}, "c2"),
        AIMessage("서울 공연은 그대로 두고 부산 공연만 취소했어요."),
    )
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)
    context = make_context("F0003")
    thread_id = str(uuid4())

    await send_message(app, thread_id, "내 티켓 하나씩 취소해 줘", context)
    first = summarize_turn(await resume_turn(app, thread_id, [{"type": "reject", "message": REJECT_MESSAGE}], context))
    assert first["pending"][0]["args"] == {"ticket_id": "T00097"}

    second = summarize_turn(await resume_turn(app, thread_id, [{"type": "approve"}], context))
    trace = rail_trace(second)
    assert trace["도구 1. cancel_ticket"]["detail"] == "사람이 거절함"
    assert trace["도구 2. cancel_ticket"]["status"] == "passed"
    assert ticket_status(context.db_path, "T00003") == "예매"
    assert ticket_status(context.db_path, "T00097") == "취소"


async def test_tool_call_error_is_not_human_rejection(monkeypatch, fake_rails, make_context, checkpointer):
    """모델이 인자를 빠뜨린 도구 호출 오류도 rail 없는 오류 결과지만, 판정 기록에서 사람 거절로 보이지 않는다."""
    fake = make_fake_model(tool_step("change_seat", {"ticket_id": "T00097"}, "c1"), AIMessage("좌석을 알려 주세요."))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)

    summary = summarize_turn(await send_message(app, str(uuid4()), "T00097 좌석 바꿔 줘", make_context("F0003")))
    event = summary["tool_events"][0]
    assert event["status"] == "error"
    assert event["rail"] == ""
    row = rail_trace(summary)["도구 1. change_seat"]
    assert row["status"] == "info"
    assert row["detail"].startswith("도구 실행 오류: ")
    assert summary["blocked_by"] == ""


async def test_lookup_in_approval_message_is_not_approval(monkeypatch, fake_rails, make_context, checkpointer):
    """조회 도구와 승인 도구를 한 메시지로 부르면 둘 다 멈추지만, 판정 기록은 승인 도구만 사람 승인 대기로 적는다."""
    calls = AIMessage(content="", tool_calls=[
        {"name": "get_my_tickets", "args": {}, "id": "c1", "type": "tool_call"},
        {"name": "cancel_ticket", "args": {"ticket_id": "T00097"}, "id": "c2", "type": "tool_call"},
    ])
    fake = make_fake_model(calls, AIMessage("취소했어요."))
    monkeypatch.setattr(builder, "llm", fake)
    app = builder.build_app(checkpointer)

    paused = await send_message(app, str(uuid4()), "내 티켓 보여 주고 T00097 취소해 줘", make_context("F0003"))
    actions = pending_actions(paused)
    assert len(actions) == 1
    assert actions[0]["name"] == "cancel_ticket"
    trace = rail_trace(summarize_turn(paused))
    assert trace["도구 1. get_my_tickets"]["detail"] == "같은 메시지의 승인을 기다리는 중(아직 실행 안 함)"
    assert trace["도구 2. cancel_ticket"]["detail"] == "사람 승인 대기"


async def test_cli_asks_pending_approval_first(monkeypatch, tmp_path, fake_rails, make_context):
    """승인 대기로 멈춘 대화를 CLI 로 다시 열면 새 메시지를 받기 전에 승인부터 묻는다."""
    from app import main

    checkpoint_path = tmp_path / "cli.sqlite"
    monkeypatch.setattr(main, "CHECKPOINT_PATH", checkpoint_path)
    fake = make_fake_model(tool_step("cancel_ticket", {"ticket_id": "T00097"}, "c1"), AIMessage("취소했어요."))
    monkeypatch.setattr(builder, "llm", fake)
    context = make_context("F0003")
    thread_id = str(uuid4())

    # 1. 승인 대기에서 멈춘 대화를 만들고 연결을 닫는다(Ctrl+C 로 끈 것과 같다)
    async with aiosqlite.connect(checkpoint_path) as connection:
        await send_message(builder.build_app(AsyncSqliteSaver(connection)), thread_id, "T00097 취소해 줘", context)

    # 2. 같은 대화 ID 로 다시 연다. 입력 질문을 차례로 기록하고 승인, exit 를 답한다
    prompts = []
    answers = ["승인", "exit"]

    def fake_input(prompt):
        prompts.append(prompt)
        return answers[len(prompts) - 1]

    monkeypatch.setattr("builtins.input", fake_input)
    await main.chat(context, thread_id)
    assert "승인할까요" in prompts[0]
    assert ticket_status(context.db_path, "T00097") == "취소"
