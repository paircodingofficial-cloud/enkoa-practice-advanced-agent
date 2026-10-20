"""그래프 층: 출력 레일이 막았을 때 한 번 다시 만들지, 바로 거절할지를 가짜 객체로 확인한다.

다시 만드는 규칙은 core/prompts.py 의 RETRY_RULES(OUT-05, OUT-09)다. 그 밖의 출력 규칙은 바로 거절한다.
"""
from langgraph.checkpoint.memory import InMemorySaver

from app.core.policies import reply_for_rule
from app.core.prompts import RETRY_RULES
from app.graph.builder import build_app
from app.graph.chat import send_message, summarize_turn
from tests.conftest import FakeRails, FakeRetriever, make_context


def answer_calls(fake_llm) -> list:
    """가짜 모델이 받은 호출 가운데 답변(검색어 다시 쓰기가 아닌) 호출만 돌려준다."""
    calls = []
    for messages in fake_llm.calls:
        if not messages[0].content.startswith("앞 대화를 참고해"):
            calls.append(messages)
    return calls


async def test_retry_then_pass_replaces_blocked_answer(fake_llm):
    # 사실 대조(OUT-05)에 처음 막히면 고칠 점을 받아 한 번 다시 쓰고, 다시 쓴 답이 통과하면 그 답이 나간다
    fake_llm.answers = ["11월 8일 오후 7시, VIP 는 5시 입장이에요.", "11월 8일 오후 7시에 시작해요."]
    rails = FakeRails(output_rules=["OUT-05", None])
    app = build_app(InMemorySaver())
    state = await send_message(app, "r-1", "팬미팅 몇 시예요?", make_context(rails=rails))
    summary = summarize_turn(state)

    assert summary["answer"] == "11월 8일 오후 7시에 시작해요."
    assert summary["output_status"] == "passed"
    assert summary["blocked_by"] == ""
    assert summary["rule_id"] == ""
    assert state["retry_count"] == 1
    assert state["retry_feedback"] == ""

    # 다시 쓴 답은 막힌 답과 같은 id 라 그 자리를 바꾼다. 대화 기록에는 질문 하나와 답 하나만 남는다
    saved = await app.aget_state({"configurable": {"thread_id": "r-1"}})
    contents = []
    for message in saved.values["messages"]:
        contents.append(message.content)
    assert contents == ["팬미팅 몇 시예요?", "11월 8일 오후 7시에 시작해요."]

    # 다시 만드는 호출에는 막힌 답 대신 고칠 점이 맨 끝에 들어가고, 고칠 점은 기록에 저장되지 않는다
    retry_prompt = answer_calls(fake_llm)[1]
    assert retry_prompt[-1].content == RETRY_RULES["OUT-05"]
    for message in retry_prompt:
        assert "VIP 는 5시" not in message.content
    assert RETRY_RULES["OUT-05"] not in contents

    # 다시 쓴 답도 출력 레일을 지났다(출력 판정 두 번)
    output_calls = 0
    for call in rails.calls:
        if call["messages"][0]["role"] == "context":
            output_calls += 1
    assert output_calls == 2


async def test_retry_then_block_refuses(fake_llm):
    # 다시 쓴 답이 또 막히면 더 만들지 않고 거절 문장으로 끝난다
    rails = FakeRails(output_rules=["OUT-09", "OUT-09"])
    summary = summarize_turn(await send_message(build_app(), "r-2", "기한 지난 티켓도 환불돼요?", make_context(rails=rails)))
    assert summary["answer"] == reply_for_rule("OUT-09")
    assert summary["rule_id"] == "OUT-09"
    assert summary["cards"] == [{"type": "blocked", "rule_id": "OUT-09", "message": reply_for_rule("OUT-09")}]
    assert len(answer_calls(fake_llm)) == 2


async def test_security_block_does_not_retry(fake_llm):
    # 보안 쪽 규칙(예: 외부 링크 OUT-08)은 위험한 맥락일 수 있어 다시 만들지 않고 바로 거절한다
    rails = FakeRails(output_rules=["OUT-08"])
    summary = summarize_turn(await send_message(build_app(), "r-3", "굿즈 어디서 사요?", make_context(rails=rails)))
    assert summary["answer"] == reply_for_rule("OUT-08")
    assert summary["rule_id"] == "OUT-08"
    assert len(answer_calls(fake_llm)) == 1


async def test_retry_reuses_this_turn_evidence(fake_llm, fake_jev, monkeypatch):
    # 다시 만들 때 검색, 티켓 조회를 다시 하지 않고 이번 턴에 모은 근거로 답만 다시 쓴다
    import app.graph.nodes as nodes

    lookups = []

    def counted_get_my_tickets(fan_id):
        lookups.append(fan_id)
        return original_get_my_tickets(fan_id)

    original_get_my_tickets = nodes.get_my_tickets
    monkeypatch.setattr(nodes, "get_my_tickets", counted_get_my_tickets)
    fake_jev.routes = {"수수료": "my_ticket_rule"}
    retriever = FakeRetriever()
    rails = FakeRails(output_rules=["OUT-05", None])
    context = make_context(fan_id="F0001", rails=rails, retriever=retriever)
    summary = summarize_turn(await send_message(build_app(), "r-4", "제 티켓 지금 취소하면 수수료 얼마예요?", context))

    assert summary["route"] == "my_ticket_rule"
    assert lookups == ["F0001"]
    assert len(retriever.queries) == 1
    # 티켓 카드가 남는다(다시 쓴 답이 통과했으므로 막힘 카드로 바뀌지 않았다)
    assert summary["cards"][0]["type"] == "ticket"
    # 두 번의 답변 호출이 같은 근거(시스템 프롬프트의 검색 문서 칸)를 받았다
    first, second = answer_calls(fake_llm)
    assert first[0].content == second[0].content


async def test_chitchat_retry_goes_back_to_chitchat(fake_llm, fake_jev):
    # 일상 대화 답이 막혀 다시 만들 때는 chitchat 이 다시 쓴다(검색 경로로 가지 않는다)
    fake_jev.routes = {"응원": "chitchat"}
    retriever = FakeRetriever()
    rails = FakeRails(output_rules=["OUT-05", None])
    summary = summarize_turn(await send_message(build_app(), "r-5", "루나 응원해!", make_context(rails=rails, retriever=retriever)))
    assert summary["route"] == "chitchat"
    assert summary["output_status"] == "passed"
    assert retriever.queries == []
    calls = answer_calls(fake_llm)
    assert len(calls) == 2
    assert "[일상 대화 규칙]" in calls[1][0].content
    assert calls[1][-1].content == RETRY_RULES["OUT-05"]


async def test_retry_count_resets_each_turn(fake_llm):
    # 다시 만든 횟수는 턴마다 비운다. 다음 턴도 한 번 다시 만들 수 있다
    rails = FakeRails(output_rules=["OUT-05", None, "OUT-05", None])
    app = build_app(InMemorySaver())
    context = make_context(rails=rails)
    first = await send_message(app, "r-6", "팬미팅 몇 시예요?", context)
    second = await send_message(app, "r-6", "응원봉은 어디서 사요?", context)
    assert first["retry_count"] == 1
    assert second["retry_count"] == 1
    assert second["output_check"]["status"] == "passed"
    assert len(answer_calls(fake_llm)) == 4
