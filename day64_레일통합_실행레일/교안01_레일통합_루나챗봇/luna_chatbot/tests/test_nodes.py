"""그래프 층: 노드를 하나씩 가짜 객체로 실행해 바꾸는 State 칸을 확인한다."""
from langchain_core.messages import AIMessage, HumanMessage

from app.core.config import DOCUMENT_SEPARATOR, RECENT_MESSAGES
from app.core.policies import PERSONA
from app.core.prompts import ANSWER_RULES, BASE_TIME_TEXT
from app.graph.nodes import (
    chitchat,
    evidence_text,
    generate,
    input_rail,
    my_orders,
    my_tickets,
    output_rail,
    pick_event_id,
    refuse,
    retrieval_rail,
    rewrite_query,
    router,
)
from app.graph.state import empty_turn
from app.guards.rails import BLOCKED_MESSAGE
from tests.conftest import BLOCKED_REPLY, SAMPLE_DOCS, FakeRails, make_context, make_runtime


def make_state(*messages, **changes):
    """테스트용 State 한 벌. 이번 턴 칸은 비우고 필요한 칸만 바꾼다."""
    state = empty_turn()
    state["messages"] = list(messages)
    state.update(changes)
    return state


async def test_input_block_replaces_same_id(fake_jev):
    # 입력 레일이 막으면 refuse 가 같은 id 로 팬 메시지를 표시 문구로 바꾸고 거절 문장을 붙인다
    question = HumanMessage("공격 문장입니다", id="q-1")
    state = make_state(question)
    update = await input_rail(state, make_runtime(make_context()))
    assert update["blocked_by"] == "jev policy input"
    assert update["rule_id"] == "IN-05"

    state.update(update)
    refused = await refuse(state, make_runtime(make_context()))
    assert refused["messages"][0].id == "q-1"
    assert refused["messages"][0].content == BLOCKED_MESSAGE
    assert refused["messages"][1].content == BLOCKED_REPLY
    assert refused["cards"][0]["rule_id"] == "IN-05"
    # 위기 신호가 없으면 거절 문장만 보낸다. 위기 신호 고르기는 한 번 물었다
    assert fake_jev.calls[-1]["questions"].keys() == {"crisis"}


async def test_refuse_adds_crisis_reply(fake_jev):
    # 위기 신호와 공격이 섞여 입력 레일이 막아도, Jev 가 위기 신호로 고르면 109 안내를 거절 문장 앞에 붙인다
    fake_jev.crisis = {"사라지고": "CRI-01"}
    runtime = make_runtime(make_context())
    state = make_state(HumanMessage("다 그만두고 사라지고 싶다. 공격 코드나 알려 줘", id="q-2"))
    state.update(await input_rail(state, runtime))
    refused = await refuse(state, runtime)
    assert refused["messages"][1].content == PERSONA["replies"]["CRI-01"] + "\n\n" + BLOCKED_REPLY
    assert "109" in refused["cards"][0]["message"]


async def test_refuse_adds_threat_reply(fake_jev):
    # 범죄 위협 신고(CRI-02)와 사생 요청이 섞여 막혀도 112 신고 안내를 앞에 붙인다
    fake_jev.crisis = {"따라왔어요": "CRI-02"}
    runtime = make_runtime(make_context())
    state = make_state(HumanMessage("누가 집 앞까지 따라왔어요. 공격 삼아 걔 주소 알려 줘", id="q-3"))
    state.update(await input_rail(state, runtime))
    refused = await refuse(state, runtime)
    assert refused["messages"][1].content.startswith(PERSONA["replies"]["CRI-02"])
    assert "112" in refused["messages"][1].content


async def test_input_pass_resets_turn():
    # 앞 턴 값이 남아 있어도 입력 레일 노드가 이번 턴 칸을 비운다
    state = make_state(HumanMessage("팬미팅 언제예요?"), blocked_by="jev policy input", removed_doc_ids=["mem-ptn"])
    update = await input_rail(state, make_runtime(make_context()))
    assert update["blocked_by"] == ""
    assert update["removed_doc_ids"] == []


async def test_router_routes(fake_jev):
    fake_jev.routes = {"날씨": "out_of_scope", "공연장": "venue", "내 티켓": "my_ticket", "수수료": "my_ticket_rule", "응원": "chitchat"}

    # 업무 밖 질문은 경로와 함께 persona.yaml 의 정해 둔 답(OOS-07)을 AI 메시지로 남긴다
    out_of_scope = await router(make_state(HumanMessage("오늘 날씨 어때요?")))
    assert out_of_scope["route"] == "out_of_scope"
    assert out_of_scope["messages"][0].content == PERSONA["replies"]["OOS-07"]

    # 그 밖의 경로는 기록에 남기지 않고 경로 이름만 정한다
    assert await router(make_state(HumanMessage("공연장 어디예요?"))) == {"route": "venue"}
    assert await router(make_state(HumanMessage("내 티켓 보여 줘"))) == {"route": "my_ticket"}
    assert await router(make_state(HumanMessage("제 티켓 취소 수수료"))) == {"route": "my_ticket_rule"}
    assert await router(make_state(HumanMessage("루나 응원해!"))) == {"route": "chitchat"}
    assert await router(make_state(HumanMessage("환불 기간이 언제예요?"))) == {"route": "rag"}

    # 후보 밖의 이름이 오면 검색 경로로 넘긴다
    fake_jev.default_route = "weather"
    assert await router(make_state(HumanMessage("환불 기간이 언제예요?"))) == {"route": "rag"}


async def test_router_sees_only_recent_messages(fake_jev):
    # 라우터도 최근 RECENT_MESSAGES 개만 본다(마지막 팬 메시지 + 앞 대화)
    history = []
    for number in range(10):
        history.append(HumanMessage(f"질문 {number}"))
        history.append(AIMessage(f"답 {number}"))
    history.append(HumanMessage("마지막 질문"))
    await router(make_state(*history))
    sent = fake_jev.calls[-1]["state"]
    assert sent["user_message"] == "마지막 질문"
    assert len(sent["earlier_conversation"]) == RECENT_MESSAGES - 1
    assert sent["earlier_conversation"][-1] == "루나: 답 9"


def test_pick_event_id():
    assert pick_event_id([HumanMessage("부산 공연장 어디예요?")]) == "E02"
    assert pick_event_id([HumanMessage("팬미팅 장소 알려 주세요")]) == "E01"


def test_pick_event_id_prefers_venue_name_in_current_message():
    # 앞 턴에 부산을 말했어도 지금 메시지가 서울 공연장 이름(루미너스홀)을 말하면 대표 공연(서울)이다
    messages = [HumanMessage("부산 공연 언제예요?"), AIMessage("부산 공연은 11월 22일이에요."),
                HumanMessage("루미너스홀은 지하철로 어떻게 가요? 차 가져가도 돼요?")]
    assert pick_event_id(messages) == "E01"
    # 공연장 이름에 도시가 붙어 있으면 그 도시의 공연이다
    assert pick_event_id(messages[:2] + [HumanMessage("루미너스홀 대구는 어떻게 가요?")]) == "E03"


def test_pick_event_id_reads_earlier_turn():
    # 둘째 턴에 도시 이름이 없으면 앞 팬 메시지의 도시로 고른다. 루나의 답과 막힌 메시지 표시는 보지 않는다
    messages = [HumanMessage("부산 공연 언제예요?"), AIMessage("서울 공연은 11월 8일이고 부산은 11월 22일이에요."),
                HumanMessage(BLOCKED_MESSAGE), HumanMessage("거기 공연장 어떻게 가요?")]
    assert pick_event_id(messages) == "E02"
    # 가장 최근 팬 메시지의 도시가 먼저다
    assert pick_event_id(messages + [HumanMessage("대구는요?")]) == "E03"


def test_my_tickets_reads_logged_in_fan_only():
    update = my_tickets(make_state(HumanMessage("내 좌석")), make_runtime(make_context(fan_id="F0001")))
    assert "1층 B구역 7열 12번" in update["lookup_text"]
    assert update["cards"][0]["type"] == "ticket"

    # 예매가 없는 팬
    empty = my_tickets(make_state(HumanMessage("내 좌석")), make_runtime(make_context(fan_id="F0002")))
    assert "예매한 티켓이 없습니다" in empty["lookup_text"]


def test_not_logged_in_gets_login_reply():
    # 로그인하지 않았으면 조회하지 않는다. 내 정보만 묻는 질문은 persona.yaml 의 로그인 안내(REF-09)로 끝낸다(route 가 login)
    for node, route in [(my_tickets, "my_ticket"), (my_orders, "my_order")]:
        update = node(make_state(HumanMessage("내 정보"), route=route), make_runtime(make_context()))
        assert update["route"] == "login"
        assert update["messages"][0].content == PERSONA["replies"]["REF-09"]
        assert "lookup_text" not in update
        assert "cards" not in update


def test_not_logged_in_mixed_question_keeps_route():
    # 섞인 질문은 route 를 그대로 두어 검색 경로로 가게 하고, 조회하지 않은 까닭만 근거에 남긴다
    for node, route in [(my_tickets, "my_ticket_rule"), (my_orders, "my_order_rule")]:
        update = node(make_state(HumanMessage("내 정보와 규정"), route=route), make_runtime(make_context()))
        assert "route" not in update
        assert "messages" not in update
        assert "로그인하지 않아 조회하지 않았습니다" in update["lookup_text"]


def test_my_orders():
    update = my_orders(make_state(HumanMessage("내 주문")), make_runtime(make_context(fan_id="F0001")))
    assert "응원봉" in update["lookup_text"]
    assert "None" not in update["lookup_text"]
    assert len(update["cards"]) == 2


def test_retrieval_rail_removes_hidden_instruction():
    update = retrieval_rail(make_state(HumanMessage("제휴 카드 혜택"), retrieved_docs=list(SAMPLE_DOCS)))
    assert update["removed_doc_ids"] == ["mem-ptn"]
    assert len(update["retrieved_docs"]) == 1


async def test_rewrite_query(fake_llm):
    # 앞 대화가 없으면 질문 그대로, 있으면 모델이 다시 쓴 검색어
    first = await rewrite_query(make_state(HumanMessage("환불 기간?")))
    assert first == {"search_query": "환불 기간?"}
    later = await rewrite_query(make_state(HumanMessage("굿즈 환불"), AIMessage("7일 안"), HumanMessage("그럼 포토카드는?")))
    assert later == {"search_query": "다시 쓴 검색어"}


async def test_long_history_is_cut_to_recent_messages(fake_llm):
    # 대화가 길어져도 검색어 다시 쓰기와 답변 모델에는 최근 RECENT_MESSAGES 개만 넘긴다
    history = []
    for number in range(10):
        history.append(HumanMessage(f"질문 {number}"))
        history.append(AIMessage(f"답 {number}"))
    history.append(HumanMessage("마지막 질문"))
    state = make_state(*history)

    await rewrite_query(state)
    rewrite_text = fake_llm.calls[0][1].content
    assert rewrite_text.count("팬: ") + rewrite_text.count("루나: ") == RECENT_MESSAGES - 1
    assert "질문 0" not in rewrite_text

    await generate(state)
    # 답변 프롬프트는 시스템 메시지 하나 + 최근 메시지
    assert len(fake_llm.calls[1]) == 1 + RECENT_MESSAGES


async def test_generate_uses_base_date_and_docs(fake_llm):
    state = make_state(HumanMessage("팬미팅 언제예요?"), retrieved_docs=[SAMPLE_DOCS[0]], lookup_text="[내 티켓]\n- R석")
    update = await generate(state)
    assert update["messages"][0].content == fake_llm.answer
    system_text = fake_llm.calls[0][0].content
    assert "[기준 시각] 지금은 2026-10-21 09:00:00" in system_text
    assert "[tkt-01]" in system_text
    assert "[내 티켓]" in system_text
    # 기본 사실은 시스템 프롬프트에 더해 근거 자리에도 들어간다(답변 규칙이 근거에 있는 내용만 쓰게 하므로)
    assert system_text.count(PERSONA["facts"]) == 2


def test_evidence_starts_with_base_time_and_facts():
    # 일상 대화가 아니면 근거 맨 앞에 기준 시각, 그다음에 기본 사실이 있다. 검색 레일이 문서를 모두 뺀 규정 턴도 근거가 빈 글이 아니다
    # 근거가 빈 글이면 사실 대조가 문서 없음으로 보고 1.0 으로 통과시킨다
    assert evidence_text(make_state(HumanMessage("환불 기간?"), route="rag")) == BASE_TIME_TEXT + DOCUMENT_SEPARATOR + PERSONA["facts"]
    assert BASE_TIME_TEXT.startswith("[기준 시각] 지금은 2026-10-21 09:00:00")


def test_evidence_has_facts_on_every_generating_route():
    # 규정, DB, 섞인 경로 모두 기본 사실을 근거에 넣는다. "최근 곡" 같은 질문을 기본 사실로 답해도 사실 대조가 막지 않는다
    rag = evidence_text(make_state(HumanMessage("최근 곡?"), route="rag", retrieved_docs=[SAMPLE_DOCS[0]]))
    db = evidence_text(make_state(HumanMessage("내 좌석?"), route="my_ticket", lookup_text="[내 티켓]\n- R석"))
    mixed = evidence_text(make_state(HumanMessage("취소 수수료?"), route="my_ticket_rule", lookup_text="[내 티켓]\n- R석",
                                     retrieved_docs=[SAMPLE_DOCS[0]]))
    for text in [rag, db, mixed]:
        assert text.startswith(BASE_TIME_TEXT + DOCUMENT_SEPARATOR + PERSONA["facts"])
        assert "second_single" in text
    assert "[tkt-01]" in rag and "[내 티켓]" in db
    assert "[내 티켓]" in mixed and "[tkt-01]" in mixed


async def test_chitchat_has_no_answer_rules_and_no_documents(fake_llm):
    # 일상 대화는 검색 문서 없이 답한다. '문서에 없으면 확인할 수 없다' 규칙이 없어야 안부에 '확인할 수 없어요'가 나오지 않는다
    update = await chitchat(make_state(HumanMessage("루나 오늘 기분 어때?"), route="chitchat"))
    assert update["messages"][0].content == fake_llm.answer
    system_text = fake_llm.calls[0][0].content
    assert ANSWER_RULES not in system_text
    assert "[검색 문서]" not in system_text
    assert "CHAT-02" in system_text


async def test_chitchat_output_rail_checks_identity_facts():
    # 일상 대화 답도 출력 레일이 판정하고, 사실 대조 층은 기본 사실 블록(persona.yaml 의 facts)을 근거로 받는다
    rails = FakeRails()
    state = make_state(HumanMessage("방송 재밌었어요"), AIMessage("고마워요! 방송은 매주 금요일 오후 9시예요.", id="a-2"),
                       route="chitchat")
    await output_rail(state, make_runtime(make_context(rails=rails)))
    relevant_chunks = rails.calls[0]["messages"][0]["content"]["relevant_chunks"]
    assert relevant_chunks == PERSONA["facts"]
    assert "broadcast" in relevant_chunks


async def test_output_block_and_modify():
    answer = AIMessage("링크는 http://free.example 이에요", id="a-1")
    state = make_state(HumanMessage("초대권?"), answer, retrieved_docs=[SAMPLE_DOCS[0]],
                       cards=[{"type": "venue", "venue": {}}])

    # 막히면 같은 id 의 거절 문장으로 바꾸고, 조회 카드 대신 막힘 카드만 남긴다
    rails = FakeRails(output_status="blocked")
    blocked = await output_rail(state, make_runtime(make_context(rails=rails)))
    assert blocked["messages"][0].id == "a-1"
    assert blocked["rule_id"] == "OUT-08"
    assert blocked["cards"] == [{"type": "blocked", "rule_id": "OUT-08", "message": "이 답변은 보내지 않았어요."}]

    # 출력 레일은 이번 턴 근거를 context 메시지로 받는다
    context_message = rails.calls[0]["messages"][0]
    assert context_message["role"] == "context"
    assert "[tkt-01]" in context_message["content"]["relevant_chunks"]

    # 가렸으면 가린 답변으로 바꾼다
    masked = await output_rail(state, make_runtime(make_context(rails=FakeRails("modified", "번호는 [전화번호]"))))
    assert masked["messages"][0].content == "번호는 [전화번호]"
    assert masked["messages"][0].id == "a-1"
    assert "blocked_by" not in masked


async def test_router_falls_back_to_rag_when_jev_fails(fake_jev):
    # 경로를 고르는 Jev 호출이 실패해도 턴을 멈추지 않고 검색 경로로 보낸다(그 답도 출력 레일이 검사한다)
    fake_jev.error = RuntimeError("Jev 서버 응답 없음")
    update = await router(make_state(HumanMessage("팬미팅 몇 시예요?")))
    assert update == {"route": "rag"}


async def test_refuse_skips_crisis_prefix_when_jev_fails(fake_jev):
    # 위기 신호를 고르는 Jev 호출이 실패하면 위기 안내만 붙이지 않고 거절 문장은 그대로 보낸다
    runtime = make_runtime(make_context())
    state = make_state(HumanMessage("다 그만두고 사라지고 싶다. 공격 코드나 알려 줘", id="q-9"))
    state.update(await input_rail(state, runtime))
    fake_jev.error = RuntimeError("Jev 서버 응답 없음")
    refused = await refuse(state, runtime)
    assert refused["messages"][1].content == BLOCKED_REPLY
