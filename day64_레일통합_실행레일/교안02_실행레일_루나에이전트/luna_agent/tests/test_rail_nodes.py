"""레일 노드 테스트: 출력 레일이 막은 답의 한 번 다시 쓰기, 보안 규칙은 바로 거절, 다시 쓰기는 도구를 다시 돌리지 않음, 판정 오류는 막고 REF-10."""
import sqlite3
from uuid import uuid4

import aiosqlite
import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from nemoguardrails.rails.llm.options import RailsResult, RailStatus

from app.core.policies import PERSONA, RAIL_ERROR_RULE
from app.core.prompts import RETRY_RULES
from app.graph import builder, nodes
from app.graph.chat import rail_trace, resume_turn, send_message, summarize_turn
from app.guards.rails import to_verdict
from tests.conftest import make_fake_model, tool_step

PASSED = {"status": "passed", "blocked_by": "", "rule_id": "", "content": ""}
REF_10 = PERSONA["replies"]["REF-10"]

# NeMo 0.23 에서 판정 액션이 오류를 냈을 때의 판정 결과(실측 모양): 막음, 레일 이름, 영어 오류 문장, 규칙 표시 없음
NEMO_ERROR_CONTENT = "I'm sorry, an internal error has occurred."


def blocked(rule_id: str, content: str, rail: str = "jev policy output") -> dict:
    """출력 레일이 막은 판정."""
    return {"status": "blocked", "blocked_by": rail, "rule_id": rule_id, "content": content}


def ticket_status(db_path, ticket_id):
    """DB 사본에서 티켓 상태를 읽는다."""
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute("SELECT status FROM tickets WHERE ticket_id = ?", (ticket_id,)).fetchone()[0]
    finally:
        connection.close()


@pytest.fixture
def output_verdicts(monkeypatch, fake_rails):
    """출력 레일 판정을 queue 에 넣은 순서대로 돌려준다. 다 쓰면 통과다. judged 에 판정한 답을 적는다."""
    state = {"queue": [], "judged": []}

    async def fake_check_output(rails, messages, documents_text):
        state["judged"].append(messages[-1].text)
        if state["queue"]:
            return state["queue"].pop(0)
        return PASSED

    monkeypatch.setattr(nodes, "check_output", fake_check_output)
    return state


@pytest.fixture
async def checkpointer(tmp_path):
    """테스트마다 새 SQLite 파일을 쓰는 비동기 체크포인터."""
    connection = await aiosqlite.connect(str(tmp_path / "chat.sqlite"))
    yield AsyncSqliteSaver(connection)
    await connection.close()


def use_models(monkeypatch, agent_steps: list, regenerate_steps: list):
    """에이전트 노드와 다시 쓰기 노드에 따로 가짜 모델을 넣고 (에이전트 모델, 다시 쓰기 모델)을 돌려준다."""
    agent_model = make_fake_model(*agent_steps)
    regenerate_model = make_fake_model(*regenerate_steps)
    monkeypatch.setattr(builder, "llm", agent_model)
    monkeypatch.setattr(nodes, "llm", regenerate_model)
    return agent_model, regenerate_model


async def test_facts_block_is_retried_once_then_passes(monkeypatch, output_verdicts, make_context, checkpointer):
    """사실 대조(OUT-05)가 막으면 도구 없이 한 번 다시 쓰고, 다시 쓴 답이 통과하면 그 답을 보낸다. 다시 쓰기 지시는 기록에 남지 않는다."""
    agent_model, regenerate_model = use_models(
        monkeypatch,
        [tool_step("get_my_tickets", {}, "c1"), AIMessage("VIP 는 오후 5시에 먼저 입장해요.")],
        [AIMessage("좌석은 1층 B구역 7열 12번이에요.")],
    )
    output_verdicts["queue"] = [blocked("OUT-05", PERSONA["replies"]["REF-08"], "jev facts output")]
    app = builder.build_app(checkpointer)

    result = await send_message(app, str(uuid4()), "내 티켓 좌석이랑 입장 시간 알려 줘", make_context("F0001"))
    summary = summarize_turn(result)
    assert summary["answer"] == "좌석은 1층 B구역 7열 12번이에요."
    assert summary["retry_count"] == 1
    assert summary["blocked_by"] == ""
    assert output_verdicts["judged"] == ["VIP 는 오후 5시에 먼저 입장해요.", "좌석은 1층 B구역 7열 12번이에요."]
    assert agent_model.count == 2
    assert regenerate_model.count == 1

    # 다시 쓰기 모델은 이번 턴의 도구 결과를 근거로 받고, 막힌 답은 받지 않으며, 맨 끝에 다시 쓰기 지시를 받는다
    prompt = regenerate_model.seen_messages[0]
    assert prompt[-1].content == RETRY_RULES["OUT-05"]
    assert any(message.type == "tool" for message in prompt)
    assert all(message.text != PERSONA["replies"]["REF-08"] for message in prompt)
    # 대화 기록에는 다시 쓴 답 하나만 남고 다시 쓰기 지시(system)는 없다
    assert [message.type for message in result["messages"]] == ["human", "ai", "tool", "ai"]
    assert "답 다시 쓰기" in rail_trace(summary)


async def test_retry_blocked_again_is_refused(monkeypatch, output_verdicts, make_context, checkpointer):
    """다시 쓴 답도 막히면 한 번 더 다시 쓰지 않고 거절 문장으로 끝난다."""
    _, regenerate_model = use_models(
        monkeypatch,
        [tool_step("get_my_tickets", {}, "c1"), AIMessage("VIP 는 오후 5시 입장이에요.")],
        [AIMessage("VIP 는 오후 4시 입장이에요.")],
    )
    refusal = PERSONA["replies"]["REF-08"]
    output_verdicts["queue"] = [blocked("OUT-05", refusal, "jev facts output"), blocked("OUT-05", refusal, "jev facts output")]
    app = builder.build_app(checkpointer)

    summary = summarize_turn(await send_message(app, str(uuid4()), "VIP 입장 시간 알려 줘", make_context("F0001")))
    assert summary["answer"] == refusal
    assert summary["retry_count"] == 1
    assert regenerate_model.count == 1
    assert summary["blocked_by"] == "jev facts output"
    assert summary["rule_id"] == "OUT-05"


async def test_security_block_is_not_retried(monkeypatch, output_verdicts, make_context, checkpointer):
    """보안 규칙(OUT-03 남의 정보)으로 막힌 답은 다시 쓰지 않고 바로 거절한다."""
    _, regenerate_model = use_models(monkeypatch, [AIMessage("F0003 님 좌석은 1층 A구역이에요.")], [AIMessage("나오면 안 되는 답")])
    output_verdicts["queue"] = [blocked("OUT-03", PERSONA["replies"]["REF-07"])]
    app = builder.build_app(checkpointer)

    summary = summarize_turn(await send_message(app, str(uuid4()), "F0003 좌석 알려 줘", make_context("F0001")))
    assert summary["answer"] == PERSONA["replies"]["REF-07"]
    assert summary["retry_count"] == 0
    assert regenerate_model.count == 0
    assert summary["rule_id"] == "OUT-03"


async def test_retry_after_approval_does_not_rerun_tool(monkeypatch, output_verdicts, make_context, checkpointer):
    """승인한 취소 뒤의 답이 OUT-09 로 막혀 다시 써도 취소 도구는 한 번만 실행되고 에이전트 모델도 다시 불리지 않는다."""
    agent_model, regenerate_model = use_models(
        monkeypatch,
        [tool_step("cancel_ticket", {"ticket_id": "T00097"}, "c1"), AIMessage("취소했고 수수료도 예외로 빼 드릴게요.")],
        [AIMessage("취소했어요. 수수료는 규정대로 빠져요.")],
    )
    output_verdicts["queue"] = [blocked("OUT-09", PERSONA["replies"]["REF-07"])]
    app = builder.build_app(checkpointer)
    context = make_context("F0003")
    thread_id = str(uuid4())

    await send_message(app, thread_id, "T00097 취소하고 수수료 빼 줘", context)
    result = await resume_turn(app, thread_id, [{"type": "approve"}], context)
    summary = summarize_turn(result)
    assert summary["answer"] == "취소했어요. 수수료는 규정대로 빠져요."
    assert summary["retry_count"] == 1
    assert ticket_status(context.db_path, "T00097") == "취소"
    cancel_results = [message for message in result["messages"] if message.type == "tool" and message.name == "cancel_ticket"]
    assert len(cancel_results) == 1
    assert agent_model.count == 2
    assert regenerate_model.count == 1


async def test_retry_count_resets_each_turn(monkeypatch, output_verdicts, make_context, checkpointer):
    """다시 쓰기 횟수는 턴마다 0 에서 시작해, 다음 턴의 막힌 답도 한 번 다시 쓴다."""
    _, regenerate_model = use_models(
        monkeypatch,
        [tool_step("get_my_tickets", {}, "c1"), AIMessage("첫 답"), tool_step("get_my_orders", {}, "c2"), AIMessage("둘째 답")],
        [AIMessage("다시 쓴 첫 답"), AIMessage("다시 쓴 둘째 답")],
    )
    refusal = PERSONA["replies"]["REF-08"]
    output_verdicts["queue"] = [blocked("OUT-05", refusal, "jev facts output"), PASSED, blocked("OUT-05", refusal, "jev facts output")]
    app = builder.build_app(checkpointer)
    context = make_context("F0001")
    thread_id = str(uuid4())

    first = summarize_turn(await send_message(app, thread_id, "내 티켓 알려 줘", context))
    second = summarize_turn(await send_message(app, thread_id, "주문은요?", context))
    assert first["answer"] == "다시 쓴 첫 답"
    assert second["answer"] == "다시 쓴 둘째 답"
    assert second["retry_count"] == 1
    assert regenerate_model.count == 2


def test_nemo_action_error_becomes_rail_error():
    """규칙 표시 없이 막힌 NeMo 판정(액션 오류)은 RAIL-ERROR 와 REF-10 안내로 바뀐다. 표시가 있는 막힘은 그대로다."""
    error = to_verdict(RailsResult(status=RailStatus.BLOCKED, content=NEMO_ERROR_CONTENT, rail="jev policy output"))
    assert error == {"status": "blocked", "blocked_by": "jev policy output", "rule_id": RAIL_ERROR_RULE, "content": REF_10}
    normal = to_verdict(RailsResult(status=RailStatus.BLOCKED, content="거절이에요. 막은 규칙: OUT-03", rail="jev policy output"))
    assert normal["rule_id"] == "OUT-03"
    assert normal["content"] == "거절이에요."


async def test_output_rail_error_refuses_without_retry(monkeypatch, output_verdicts, make_context, checkpointer):
    """출력 레일 판정이 오류로 끝나면 다시 쓰지 않고 REF-10 으로 답한다."""
    _, regenerate_model = use_models(monkeypatch, [AIMessage("안녕하세요!")], [AIMessage("나오면 안 되는 답")])
    error_result = RailsResult(status=RailStatus.BLOCKED, content=NEMO_ERROR_CONTENT, rail="jev policy output")
    output_verdicts["queue"] = [to_verdict(error_result)]
    app = builder.build_app(checkpointer)

    summary = summarize_turn(await send_message(app, str(uuid4()), "안녕", make_context("F0001")))
    assert summary["answer"] == REF_10
    assert summary["rule_id"] == RAIL_ERROR_RULE
    assert regenerate_model.count == 0


async def test_input_rail_error_refuses_before_model(monkeypatch, fake_rails, make_context, checkpointer):
    """입력 레일 판정이 오류로 끝나면 모델과 도구를 부르지 않고 REF-10 으로 답한다."""
    fake_rails["input"] = to_verdict(RailsResult(status=RailStatus.BLOCKED, content=NEMO_ERROR_CONTENT, rail="jev policy input"))
    agent_model, _ = use_models(monkeypatch, [AIMessage("나오면 안 되는 답")], [])
    app = builder.build_app(checkpointer)

    summary = summarize_turn(await send_message(app, str(uuid4()), "내 티켓 알려 줘", make_context("F0001")))
    assert summary["answer"] == REF_10
    assert summary["blocked_by"] == "jev policy input"
    assert agent_model.count == 0


async def test_fanart_policy_judge_error_blocks_before_image(monkeypatch, fake_rails, fake_image, make_context, checkpointer):
    """그림 요청 판정(Jev)이 오류를 내면 통과시키지 않고 RAIL-ERROR 로 막는다. 그림 API 는 부르지 않는다."""
    fake_image["error"] = "jev"
    use_models(monkeypatch, [tool_step("create_fanart", {"request": "별빛 무대 루나"}, "c1"), AIMessage("지금은 못 만들어요.")], [])
    app = builder.build_app(checkpointer)

    summary = summarize_turn(await send_message(app, str(uuid4()), "별빛 무대 루나 그려 줘", make_context("F0001")))
    event = summary["tool_events"][0]
    assert event["status"] == "error"
    assert event["rule_id"] == RAIL_ERROR_RULE
    assert event["content"] == REF_10
    assert fake_image["calls"]["generate"] == 0


async def test_moderation_error_deletes_image(monkeypatch, tmp_path, fake_rails, fake_image, make_context, checkpointer):
    """만든 그림의 모더레이션이 오류를 내면 검사하지 못한 그림을 지우고 RAIL-ERROR 로 막는다."""
    fake_image["error"] = "moderation"
    use_models(monkeypatch, [tool_step("create_fanart", {"request": "별빛 무대 루나"}, "c1"), AIMessage("보여 드리지 못했어요.")], [])
    app = builder.build_app(checkpointer)

    summary = summarize_turn(await send_message(app, str(uuid4()), "별빛 무대 루나 그려 줘", make_context("F0001")))
    event = summary["tool_events"][0]
    assert event["rail"] == "check_fanart_image"
    assert event["rule_id"] == RAIL_ERROR_RULE
    assert event["content"] == REF_10
    assert event["artifact"]["path"] is None
    assert fake_image["calls"]["generate"] == 1
    assert list((tmp_path / "fanart").glob("*.png")) == []
