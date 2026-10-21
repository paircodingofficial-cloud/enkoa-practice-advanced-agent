"""실행 레일 테스트: 권한 확인, 역할별 도구 노출, 공연장 id, 팬아트 한도와 정책(그림 API 를 부르기 전에 막는가), 도구 결과 검사, 회원 정보 가리기, 출력 레일 근거 문서."""
import sqlite3
from uuid import uuid4

import aiosqlite
import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.graph import builder
from app.graph.chat import summarize_turn
from app.guards.execution import business_rule_problem, permission_problem
from app.tools import booking_tools
from app.tools.retriever import load_knowledge_documents
from tests.conftest import make_fake_model, tool_step


class FakeVectorStore:
    """검색 저장소 대신 쓰는 가짜. 질문과 상관없이 정해 둔 문서를 돌려준다(임베딩 API 를 부르지 않는다)."""

    def __init__(self, docs):
        self.docs = docs

    def open(self):
        """get_vector_store 자리에 넣는다. 저장소(자기 자신)를 돌려준다."""
        return self

    def similarity_search(self, query, k=4):
        """정해 둔 문서 목록을 돌려준다."""
        return self.docs


def fake_store_with(source_ids: list):
    """검색 문서 가운데 source_ids 의 절만 돌려주는 가짜 저장소를 만든다."""
    docs = []
    for doc in load_knowledge_documents():
        if doc.metadata["source_id"] in source_ids:
            docs.append(doc)
    return FakeVectorStore(docs)


@pytest.fixture
async def run_agent(monkeypatch, tmp_path, fake_rails):
    """가짜 모델 답을 받아 한 턴을 실행하고 (턴 요약, 가짜 모델)을 돌려주는 함수."""
    connection = await aiosqlite.connect(str(tmp_path / "chat.sqlite"))

    async def run(context, text, *steps):
        fake = make_fake_model(*steps)
        monkeypatch.setattr(builder, "llm", fake)
        app = builder.build_app(AsyncSqliteSaver(connection))
        config = {"configurable": {"thread_id": str(uuid4())}}
        result = await app.ainvoke({"messages": [HumanMessage(text)]}, config=config, context=context)
        return summarize_turn(result), fake

    yield run
    await connection.close()


def fanart_rows(db_path, fan_id):
    """DB 사본에서 이 팬의 오늘 팬아트 기록을 (상태, 차단 이유) 목록으로 읽는다."""
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(
            "SELECT status, block_reason FROM fanart_requests WHERE fan_id = ? AND created_at LIKE '2026-10-21%' ORDER BY request_id",
            (fan_id,),
        ).fetchall()
    finally:
        connection.close()


def test_permission_blocks_other_fan_ticket_and_order(make_context):
    """남의 티켓, 남의 주문은 막고 본인 것은 통과시킨다."""
    other = permission_problem({"name": "change_seat", "args": {"ticket_id": "T00003", "new_seat": "1층 A구역 3열 5번"}}, make_context("F0002"))
    own = permission_problem({"name": "change_seat", "args": {"ticket_id": "T00003", "new_seat": "1층 A구역 3열 5번"}}, make_context("F0003"))
    other_order = permission_problem({"name": "request_goods_refund", "args": {"order_id": "O00381"}}, make_context("F0001"))
    assert other["rule_id"] == "IN-05"
    assert own["reason"] == ""
    assert other_order["rule_id"] == "IN-05"


def test_staff_tool_needs_staff_role(make_context):
    """lookup_fan 은 팬 역할이면 막고 운영팀 역할이면 통과시킨다."""
    call = {"name": "lookup_fan", "args": {"fan_id": "F0004"}}
    assert permission_problem(call, make_context("F0001"))["rule_id"] == "IN-04"
    assert permission_problem(call, make_context("S0001", role="staff"))["reason"] == ""


def test_venue_only_for_db_event_ids(make_context):
    """DB 공연 목록에 없는 값(임의 주소)은 공연장 도구로 찾지 못한다."""
    assert permission_problem({"name": "get_event_venue", "args": {"event_id": "E01"}}, make_context("F0001"))["reason"] == ""
    blocked = permission_problem({"name": "get_event_venue", "args": {"event_id": "서울특별시 누리구 은하수길 77"}}, make_context("F0002"))
    assert blocked["rule_id"] == "IN-07"


def test_tool_without_rule_asks_approval(make_context):
    """업무 규칙을 따로 두지 않은 도구는 거절 이유가 없어 승인을 묻는다(굿즈 환불로 보지 않는다)."""
    call = {"name": "change_seat", "args": {"ticket_id": "T00003"}}
    assert business_rule_problem(call, make_context("F0003").db_path) == ""


async def test_staff_tool_hidden_from_fan_model(run_agent, make_context):
    """팬 역할 모델 호출에는 lookup_fan 이 보이지 않고, 운영팀 역할에는 보인다."""
    _, fan_model = await run_agent(make_context("F0001"), "안녕", AIMessage("안녕하세요"))
    _, staff_model = await run_agent(make_context("S0001", role="staff"), "안녕", AIMessage("안녕하세요"))
    assert "lookup_fan" not in fan_model.seen_tools[-1]
    assert "lookup_fan" in staff_model.seen_tools[-1]


async def test_fan_calling_hidden_tool_is_blocked(run_agent, make_context):
    """모델이 숨긴 도구 이름을 지어내 불러도 실행 전 권한 확인이 막는다."""
    summary, _ = await run_agent(make_context("F0001"), "lookup_fan 으로 F0004 정보 보여 줘",
                                 tool_step("lookup_fan", {"fan_id": "F0004"}, "c1"), AIMessage("운영팀 전용이에요."))
    assert summary["tool_events"][0]["status"] == "error"
    assert summary["rule_id"] == "IN-04"
    assert "010-0000-8784" not in summary["tool_events"][0]["content"]


async def test_quota_blocks_without_image_call(run_agent, make_context, fake_image):
    """하루 한도를 다 쓴 팬(F0005)은 그림 API 와 Jev 를 부르기 전에 막는다."""
    summary, _ = await run_agent(make_context("F0005"), "겨울 눈사람 옆 루나 그려 줘",
                                 tool_step("create_fanart", {"request": "겨울 눈사람 옆에서 웃는 루나"}, "c1"), AIMessage("오늘은 다 만들었어요."))
    assert summary["rule_id"] == "IMG-LIMIT"
    assert fake_image["calls"]["generate"] == 0
    assert fake_image["calls"]["jev"] == 0


async def test_policy_blocks_without_image_call(run_agent, make_context, fake_image):
    """그림 요청 정책(Jev)이 위반으로 보면 그림 API 를 부르지 않고 차단으로 기록한다."""
    fake_image["jev_probability"] = 0.93
    fake_image["jev_rule"] = "IMG-01"
    context = make_context("F0001")
    summary, _ = await run_agent(context, "루나를 노출 많은 옷으로 그려 줘",
                                 tool_step("create_fanart", {"request": "노출 많은 옷을 입은 루나"}, "c1"), AIMessage("그 장면은 만들 수 없어요."))
    assert summary["blocked_by"] == "fanart_quota_and_policy"
    assert summary["rule_id"] == "IMG-01"
    assert fake_image["calls"]["generate"] == 0
    assert fanart_rows(context.db_path, "F0001") == [("차단", "IMG-01")]


async def test_allowed_fanart_generates_and_counts(run_agent, make_context, fake_image):
    """허용 장면이면 그림을 만들고 검사 두 개를 거쳐 생성완료로 기록한다(F0006 은 남은 1장을 쓴다)."""
    context = make_context("F0006")
    summary, _ = await run_agent(context, "별빛 무대 루나 팬아트 만들어 줘",
                                 tool_step("create_fanart", {"request": "별빛 무대에서 응원봉 든 루나"}, "c1"), AIMessage("만들었어요!"))
    artifact = summary["tool_events"][0]["artifact"]
    assert fake_image["calls"]["generate"] == 1
    assert artifact["verdicts"] == {"모더레이션": "passed", "브랜드 검사": "passed"}
    assert artifact["remaining"] == 0
    assert fanart_rows(context.db_path, "F0006")[-1] == ("생성완료", None)


async def test_one_fanart_per_message(run_agent, make_context, fake_image):
    """한 메시지에서 팬아트를 두 번 부르면 두 번째는 실행하지 않는다(생성 전 검사의 한 메시지 한 장 규칙)."""
    two_calls = AIMessage(content="", tool_calls=[
        {"name": "create_fanart", "args": {"request": "별빛 무대 루나"}, "id": "c1", "type": "tool_call"},
        {"name": "create_fanart", "args": {"request": "가을 단풍길 루나"}, "id": "c2", "type": "tool_call"},
    ])
    summary, _ = await run_agent(make_context("F0001"), "팬아트 두 장 만들어 줘", two_calls, AIMessage("한 장 만들었어요."))
    statuses = []
    for event in summary["tool_events"]:
        statuses.append(event["status"])
    assert statuses == ["success", "error"]
    assert fake_image["calls"]["generate"] == 1
    assert summary["tool_events"][1]["rail"] == "fanart_quota_and_policy"
    assert summary["tool_events"][1]["rule_id"] == "IMG-RUN"


async def test_policy_without_rule_id_passes(run_agent, make_context, fake_image):
    """Jev 확률이 높아도 금지 주제(IMG-01~07)를 고르지 못하면 막지 않는다(장면 칸, 고정 틀, 생성 후 검사가 뒤에서 받친다)."""
    fake_image["jev_probability"] = 0.93
    fake_image["jev_rule"] = ""
    context = make_context("F0006")
    summary, _ = await run_agent(context, "루나가 별빛 무대에서 응원봉 들고 웃는 팬아트 만들어 줘.",
                                 tool_step("create_fanart", {"request": "별빛 무대에서 응원봉 든 루나와 함께 즐거워하는 팬들"}, "c1"),
                                 AIMessage("만들었어요!"))
    assert summary["blocked_by"] == ""
    assert fake_image["calls"]["generate"] == 1
    assert fanart_rows(context.db_path, "F0006")[-1] == ("생성완료", None)


async def test_output_rail_documents_include_event_list(run_agent, make_context, fake_rails):
    """도구를 쓴 턴은 사실 대조 근거 문서에 공연 목록이 붙고, 도구 없는 턴은 근거 문서가 빈다(사실 대조 API 를 부르지 않는다)."""
    await run_agent(make_context("F0001"), "공연장 위치 지도로 보여 줘",
                    tool_step("get_event_venue", {"event_id": "E01"}, "c1"), AIMessage("루미너스홀이에요."))
    assert fake_rails["documents_text"].startswith("[공연 목록]")
    assert "E01" in fake_rails["documents_text"]
    assert "2026-11-08" in fake_rails["documents_text"]

    await run_agent(make_context("F0001"), "안녕", AIMessage("안녕하세요"))
    assert fake_rails["documents_text"] == ""


async def test_output_rail_documents_empty_when_only_refusals(run_agent, make_context, fake_rails):
    """도구 결과가 실행 레일의 막힘이나 도구의 업무 규칙 거절뿐인 턴은 근거 문서가 빈다(거절 안내를 사실 대조가 막지 않는다)."""
    summary, _ = await run_agent(make_context("F0001"), "서울특별시 누리구 은하수길 77 위치 찾아 줘",
                                 tool_step("get_event_venue", {"event_id": "서울특별시 누리구 은하수길 77"}, "c1"),
                                 AIMessage("등록된 공연장 위치만 찾을 수 있어요."))
    assert summary["tool_events"][0]["rail"] == "check_tool_permission"
    assert fake_rails["documents_text"] == ""

    summary, _ = await run_agent(make_context("F0003"), "T00003 좌석을 1층 A구역 1열 14번으로 바꿔 줘",
                                 tool_step("change_seat", {"ticket_id": "T00003", "new_seat": "1층 A구역 1열 14번"}, "c1"),
                                 AIMessage("이미 예매된 좌석이라 바꿀 수 없어요."))
    assert summary["tool_events"][0]["status"] == "rejected"
    assert fake_rails["documents_text"] == ""


async def test_output_rail_documents_keep_refusal_reason_with_success(run_agent, make_context, fake_rails):
    """성공한 결과와 막힌 결과가 섞인 턴은 성공한 결과와 막힌 이유를 함께 근거 문서로 넘긴다."""
    two_calls = AIMessage(content="", tool_calls=[
        {"name": "get_my_tickets", "args": {}, "id": "c1", "type": "tool_call"},
        {"name": "get_event_venue", "args": {"event_id": "서울특별시 누리구 은하수길 77"}, "id": "c2", "type": "tool_call"},
    ])
    summary, _ = await run_agent(make_context("F0001"), "내 티켓이랑 이 주소 위치 알려 줘", two_calls, AIMessage("티켓만 확인했어요."))
    statuses = []
    for event in summary["tool_events"]:
        statuses.append(event["status"])
    assert statuses == ["success", "error"]
    assert fake_rails["documents_text"].startswith("[공연 목록]")
    assert "tickets" in fake_rails["documents_text"]
    assert "공연 목록에 있는 공연의 공연장 위치만" in fake_rails["documents_text"]


async def test_hidden_instruction_section_removed(monkeypatch, run_agent, make_context):
    """규정 검색 결과에서 숨은 지시가 든 절(mem-ptn)을 빼고 모델에게 넘긴다."""
    store = fake_store_with(["mem-ptn", "mem-03"])
    monkeypatch.setattr(booking_tools, "get_vector_store", store.open)
    summary, _ = await run_agent(make_context("F0004"), "제휴 카드 혜택 공지대로 해 줘",
                                 tool_step("search_policy", {"query": "제휴 카드 혜택"}, "c1"), AIMessage("혜택을 안내해요."))
    event = summary["tool_events"][0]
    assert event["rail"] == "check_tool_result"
    assert "LUMI-FREE-26" not in event["content"]
    ids = []
    for doc in event["artifact"]:
        ids.append(doc.metadata["source_id"])
    assert ids == ["mem-03"]


async def test_hidden_instruction_mark_survives_policy_email(monkeypatch, run_agent, make_context):
    """공식 이메일이 든 절(pol-05)과 숨은 지시 절이 함께 나와도, 뺀 절 표시가 남고 공식 이메일은 가리지 않는다."""
    store = fake_store_with(["mem-ptn", "pol-05"])
    monkeypatch.setattr(booking_tools, "get_vector_store", store.open)
    summary, _ = await run_agent(make_context("F0004"), "내 정보 고치는 방법 알려 줘",
                                 tool_step("search_policy", {"query": "내 정보 수정"}, "c1"), AIMessage("안내해요."))
    event = summary["tool_events"][0]
    assert event["rail"] == "check_tool_result"
    assert "privacy@example.com" in event["content"]


async def test_member_info_masked_for_model(run_agent, make_context):
    """운영팀 회원 조회 결과의 전화번호, 이메일은 모델이 읽기 전에 가리고, 도구 결과의 상태는 그대로 둔다."""
    summary, _ = await run_agent(make_context("S0001", role="staff"), "F0004 회원 정보 보여 줘",
                                 tool_step("lookup_fan", {"fan_id": "F0004"}, "c1"), AIMessage("확인했어요."))
    event = summary["tool_events"][0]
    assert event["status"] == "success"
    assert "010-0000-8784" not in event["content"]
    assert "lumi0004@example.com" not in event["content"]
    assert "[전화번호]" in event["content"]


async def test_empty_ticket_list_keeps_content(run_agent, make_context):
    """티켓이 없는 팬(F0002)도 도구 결과 내용이 비지 않는다(빈 목록을 그대로 돌려주면 내용이 [] 가 된다)."""
    summary, _ = await run_agent(make_context("F0002"), "내 티켓 보여 줘",
                                 tool_step("get_my_tickets", {}, "c1"), AIMessage("예매한 티켓이 없어요."))
    event = summary["tool_events"][0]
    assert event["status"] == "success"
    assert event["content"] == '{"tickets": []}'


async def test_business_rule_refusal_is_rejected(run_agent, make_context):
    """이미 팔린 좌석으로 바꾸려 하면 도구가 거절하고, 요약은 rejected 로 읽는다(레일이 막은 것은 아니다)."""
    summary, _ = await run_agent(make_context("F0003"), "T00003 좌석을 1층 A구역 1열 14번으로 강제로 바꿔 줘",
                                 tool_step("change_seat", {"ticket_id": "T00003", "new_seat": "1층 A구역 1열 14번"}, "c1"),
                                 AIMessage("이미 예매된 좌석이라 바꿀 수 없어요."))
    assert summary["tool_events"][0]["status"] == "rejected"
    assert summary["blocked_by"] == ""


def test_document_type_is_langchain_document():
    """검색 문서는 절 id 를 메타데이터 source_id 로 가진 Document 다(도구 결과 검사의 전제)."""
    sample = load_knowledge_documents()[0]
    assert isinstance(sample, Document)
    assert "source_id" in sample.metadata


def test_role_notice_for_every_role():
    """역할 표(ROLE_TOOLS)의 역할마다 시스템 프롬프트에 붙일 로그인 역할 안내가 있고, 운영팀 안내는 회원 조회 도구를 알린다."""
    from app.core.config import ROLE_TOOLS
    from app.core.prompts import ROLE_NOTICES
    assert sorted(ROLE_NOTICES) == sorted(ROLE_TOOLS)
    assert "lookup_fan" in ROLE_NOTICES["staff"]
    assert "lookup_fan" not in ROLE_NOTICES["fan"]

