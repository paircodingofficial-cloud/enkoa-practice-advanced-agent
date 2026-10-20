"""그래프 층: 실제 그래프를 가짜 객체로 컴파일해 여러 턴 대화와 경로마다 어느 노드를 지나는지 확인한다."""
import aiosqlite
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.policies import PERSONA
from app.graph.builder import build_app
from app.graph.chat import send_message, summarize_turn
from app.guards.rails import BLOCKED_MESSAGE
from tests.conftest import FakeRails, FakeRetriever, make_context

# 가짜 Jev 가 고르는 경로: 팬 메시지에 낱말이 있으면 그 경로, 없으면 rag
ROUTER_PICKS = {
    "날씨": "out_of_scope",
    "공연장": "venue",
    "내 티켓": "my_ticket",
    "수수료": "my_ticket_rule",
    "응원": "chitchat",
    "안녕": "chitchat",
}


def rewrite_calls(fake_llm) -> int:
    """가짜 모델이 받은 호출 가운데 검색어 다시 쓰기 호출 수를 돌려준다."""
    count = 0
    for messages in fake_llm.calls:
        if messages[0].content.startswith("앞 대화를 참고해"):
            count += 1
    return count


async def test_blocked_turn_then_normal_turn(tmp_path, fake_llm, fake_jev):
    fake_jev.routes = ROUTER_PICKS
    rails = FakeRails()
    context = make_context(fan_id="F0001", rails=rails)
    async with aiosqlite.connect(tmp_path / "chat.sqlite") as connection:
        app = build_app(AsyncSqliteSaver(connection))

        # 1턴: 입력 레일이 막는다. 답변 모델은 부르지 않는다
        first = summarize_turn(await send_message(app, "t-1", "공격 문장입니다", context))
        assert first["route"] == "refuse"
        assert first["rule_id"] == "IN-05"
        assert fake_llm.calls == []

        # 2턴: 같은 대화 ID 라 1턴 기록이 이어진다. 막힌 질문은 표시 문구로 바뀌어 있다
        second_state = await send_message(app, "t-1", "팬미팅 몇 시예요?", context)
        second = summarize_turn(second_state)
        assert second["route"] == "rag"
        assert second["blocked_by"] == ""
        assert second["removed_doc_ids"] == ["mem-ptn"]
        assert second["retrieved_ids"] == ["tkt-01"]
        assert second["search_query"] == "다시 쓴 검색어"

        saved = await app.aget_state({"configurable": {"thread_id": "t-1"}})
        contents = []
        for message in saved.values["messages"]:
            contents.append(message.content)
        assert len(contents) == 4
        assert contents[0] == BLOCKED_MESSAGE
        assert contents[3] == fake_llm.answer

    # 2턴 입력 판정에는 사람 메시지와 도구 호출 없는 AI 답만 들어갔다
    second_input_roles = []
    for message in rails.calls[1]["messages"]:
        second_input_roles.append(message["role"])
    assert second_input_roles == ["user", "assistant", "user"]


async def test_out_of_scope_ends_without_model(fake_llm, fake_jev):
    # 업무 밖 질문은 라우터가 정해 둔 답(OOS-07)으로 끝낸다(출력 레일, 답변 모델 없음)
    fake_jev.routes = ROUTER_PICKS
    out_of_scope = summarize_turn(await send_message(build_app(), "t-2", "오늘 날씨 어때요?", make_context()))
    assert out_of_scope["route"] == "out_of_scope"
    assert out_of_scope["answer"] == PERSONA["replies"]["OOS-07"]
    assert out_of_scope["output_status"] == ""
    assert fake_llm.calls == []


async def test_router_reads_recent_turns(fake_llm, fake_jev):
    # 라우터는 마지막 팬 메시지와 함께 앞 대화도 Jev 에게 넘긴다("거기 어떻게 가요?" 가 가리키는 곳을 알 수 있게)
    fake_jev.routes = ROUTER_PICKS
    app = build_app(InMemorySaver())
    context = make_context()
    await send_message(app, "t-9", "오늘 날씨 어때요?", context)
    await send_message(app, "t-9", "거기 공연장 어떻게 가요?", context)
    last_state = fake_jev.calls[-1]["state"]
    assert last_state["user_message"] == "거기 공연장 어떻게 가요?"
    assert last_state["earlier_conversation"] == ["팬: 오늘 날씨 어때요?", "루나: " + PERSONA["replies"]["OOS-07"]]


async def test_unusable_route_falls_back_to_rag(fake_llm, fake_jev):
    # Jev 가 후보 밖의 이름을 돌려주면 검색 경로(rag)로 간다
    fake_jev.default_route = "weather"
    odd = summarize_turn(await send_message(build_app(), "t-10", "환불 기간이 언제예요?", make_context()))
    assert odd["route"] == "rag"


async def test_chitchat_route_skips_retrieval(fake_llm, fake_jev):
    # 일상 대화는 검색하지 않고 답한 뒤 출력 레일을 지난다. 인사도 일상 대화로 루나 말투로 답한다
    fake_jev.routes = ROUTER_PICKS
    retriever = FakeRetriever()
    rails = FakeRails()
    context = make_context(rails=rails, retriever=retriever)
    chat = summarize_turn(await send_message(build_app(), "t-3", "루나 오늘도 응원해!", context))
    assert chat["route"] == "chitchat"
    assert chat["answer"] == fake_llm.answer
    assert chat["output_status"] == "passed"
    assert retriever.queries == []
    assert chat["retrieved_ids"] == []
    assert len(fake_llm.calls) == 1
    assert rewrite_calls(fake_llm) == 0

    # 인사도 정해 둔 문장이 아니라 일상 대화로 답한다
    greeting = summarize_turn(await send_message(build_app(), "t-11", "루나야 안녕!", context))
    assert greeting["route"] == "chitchat"
    assert greeting["answer"] == fake_llm.answer


async def test_db_routes_skip_rewrite_and_retrieval(fake_llm, fake_jev):
    # 공연장, 내 티켓 질문은 DB 사실만으로 답한다. 검색어 다시 쓰기, 검색을 부르지 않는다
    fake_jev.routes = ROUTER_PICKS
    retriever = FakeRetriever()
    rails = FakeRails()
    context = make_context(fan_id="F0001", rails=rails, retriever=retriever)
    app = build_app()

    venue = summarize_turn(await send_message(app, "t-4", "부산 공연장 어디예요?", context))
    assert venue["route"] == "venue"
    assert venue["cards"][0]["venue"]["name"] == "루미너스홀 부산"
    # 검색하지 않으므로 "언제 어디서" 에도 답하도록 공연장 조회 글에 공연 시작 시각이 들어 있다
    assert venue["contexts"][0].startswith("[기준 시각]")
    assert venue["contexts"][1].startswith("[공연장]")
    assert "공연 시작: 2026-11-22 18:00:00" in venue["contexts"][1]
    # 답변 모델과 사실 대조가 받은 기본 사실도 평가 근거 끝에 들어간다
    assert venue["contexts"][-1].startswith("[기본 사실]")
    assert venue["search_query"] == ""
    assert venue["retrieved_ids"] == []

    ticket = summarize_turn(await send_message(app, "t-5", "내 티켓 좌석 어디예요?", context))
    assert ticket["route"] == "my_ticket"
    assert ticket["cards"][0]["ticket"]["seat"] == "1층 B구역 7열 12번"
    assert ticket["output_status"] == "passed"
    assert ticket["retrieved_ids"] == []

    assert retriever.queries == []
    assert rewrite_calls(fake_llm) == 0
    # 출력 레일 사실 대조는 기준 시각 다음에 DB 사실을 문서로 받는다
    relevant_chunks = rails.calls[-1]["messages"][0]["content"]["relevant_chunks"]
    assert relevant_chunks.startswith("[기준 시각]")
    assert "[내 티켓]" in relevant_chunks


async def test_mixed_question_gets_db_facts_and_documents(fake_llm, fake_jev):
    # 내 티켓과 규정을 함께 묻는 질문은 티켓을 조회한 뒤 검색 경로로 가서, 답변 모델이 둘 다 받는다
    fake_jev.routes = ROUTER_PICKS
    retriever = FakeRetriever()
    rails = FakeRails()
    context = make_context(fan_id="F0001", rails=rails, retriever=retriever)
    mixed = summarize_turn(await send_message(build_app(), "t-6", "제 티켓 지금 취소하면 수수료 얼마예요?", context))
    assert mixed["route"] == "my_ticket_rule"
    assert mixed["retrieved_ids"] == ["tkt-01"]
    assert mixed["contexts"][1].startswith("[내 티켓]")
    assert retriever.queries == ["제 티켓 지금 취소하면 수수료 얼마예요?"]

    answer_system_text = fake_llm.calls[-1][0].content
    assert "1층 B구역 7열 12번" in answer_system_text
    assert "[tkt-01]" in answer_system_text
    relevant_chunks = rails.calls[-1]["messages"][0]["content"]["relevant_chunks"]
    assert "[내 티켓]" in relevant_chunks
    assert "[tkt-01]" in relevant_chunks
    # "지금 취소하면" 처럼 '지금'에 기대는 답이 막히지 않게 사실 대조도 답변 모델과 같은 기준 시각을 받는다
    assert "[기준 시각]" in relevant_chunks
    assert relevant_chunks in answer_system_text


async def test_not_logged_in_ticket_question_ends_with_login_reply(fake_llm, fake_jev):
    # 로그인하지 않은 팬의 내 티켓 질문은 조회, 검색, 답변 모델, 출력 레일 없이 로그인 안내로 끝난다
    fake_jev.routes = ROUTER_PICKS
    retriever = FakeRetriever()
    context = make_context(retriever=retriever)
    login = summarize_turn(await send_message(build_app(), "t-7", "내 티켓 좌석 어디예요?", context))
    assert login["route"] == "login"
    assert login["answer"] == PERSONA["replies"]["REF-09"]
    assert login["output_status"] == ""
    assert login["cards"] == []
    assert retriever.queries == []
    assert fake_llm.calls == []


async def test_not_logged_in_mixed_question_still_answers_rule(fake_llm, fake_jev):
    # 로그인하지 않은 팬의 섞인 질문은 티켓 조회만 건너뛰고 검색 경로로 가서 규정 부분에 답한다
    fake_jev.routes = ROUTER_PICKS
    retriever = FakeRetriever()
    rails = FakeRails()
    context = make_context(rails=rails, retriever=retriever)
    mixed = summarize_turn(await send_message(build_app(), "t-8", "제 티켓 지금 취소하면 수수료 얼마예요?", context))
    assert mixed["route"] == "my_ticket_rule"
    assert mixed["answer"] == fake_llm.answer
    assert mixed["output_status"] == "passed"
    assert mixed["retrieved_ids"] == ["tkt-01"]
    assert mixed["cards"] == []
    assert retriever.queries == ["제 티켓 지금 취소하면 수수료 얼마예요?"]
    # 답변 모델은 조회하지 않은 까닭을 근거로 받는다(티켓을 지어내지 않고 로그인을 권하게 한다)
    assert "로그인하지 않아 조회하지 않았습니다" in fake_llm.calls[-1][0].content
