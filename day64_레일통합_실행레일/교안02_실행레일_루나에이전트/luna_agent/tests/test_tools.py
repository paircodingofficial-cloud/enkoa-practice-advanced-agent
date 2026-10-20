"""도구 테스트: 쓰기 도구가 DB 임시 사본만 고치고, 규정에 맞지 않는 요청은 이유와 함께 거절한다."""
import sqlite3
from types import SimpleNamespace

from app.core.config import DB_PATH
from app.tools.booking_tools import cancel_ticket, change_seat, get_event_venue, get_my_orders, get_my_profile, get_my_tickets, request_goods_refund, seat_in_area


def runtime_for(context):
    """도구 함수에 넘길 runtime 자리(context 만 읽는다)."""
    return SimpleNamespace(context=context)


def read_one(db_path, query, params):
    """DB 에서 한 행을 읽는다."""
    connection = sqlite3.connect(db_path)
    try:
        return connection.execute(query, params).fetchone()
    finally:
        connection.close()


def test_seat_area_parsing():
    """좌석이 등급 구역 범위 안에 있는지 판단한다."""
    area = "1층 B구역 1~10열 1~25번, 1층 C구역 1~10열 1~25번"
    assert seat_in_area("1층 C구역 10열 25번", area)
    assert not seat_in_area("1층 C구역 11열 1번", area)
    assert not seat_in_area("1층 A구역 3열 5번", area)
    assert not seat_in_area("아무 글", area)


def test_change_seat_writes_copy_only(make_context):
    """좌석 변경은 사본 DB 에만 쓰이고 원본은 그대로다."""
    context = make_context("F0003")
    result = change_seat.func(ticket_id="T00003", new_seat="1층 A구역 3열 5번", runtime=runtime_for(context))
    assert result["result"] == "좌석 변경 완료"
    assert read_one(context.db_path, "SELECT seat FROM tickets WHERE ticket_id = ?", ("T00003",))[0] == "1층 A구역 3열 5번"
    assert read_one(DB_PATH, "SELECT seat FROM tickets WHERE ticket_id = ?", ("T00003",))[0] == "1층 A구역 9열 14번"


def test_change_seat_refuses_taken_or_other_grade(make_context):
    """이미 팔린 좌석과 다른 등급 좌석으로는 바꾸지 않는다."""
    context = make_context("F0003")
    taken = change_seat.func(ticket_id="T00003", new_seat="1층 A구역 1열 14번", runtime=runtime_for(context))
    other_grade = change_seat.func(ticket_id="T00003", new_seat="1층 B구역 1열 1번", runtime=runtime_for(context))
    assert "이미 예매된" in taken["error"]
    assert "구역" in other_grade["error"]
    assert read_one(context.db_path, "SELECT seat FROM tickets WHERE ticket_id = ?", ("T00003",))[0] == "1층 A구역 9열 14번"


def test_cancel_ticket_records_fee_and_refund(make_context):
    """부산 공연 32일 전 취소는 수수료 없이 전액을 돌려준다."""
    context = make_context("F0003")
    result = cancel_ticket.func(ticket_id="T00097", runtime=runtime_for(context))
    assert result == {"ticket_id": "T00097", "cancel_fee": 0, "refund_amount": 88000, "result": "예매 취소 완료"}
    row = read_one(context.db_path, "SELECT status, cancel_fee, refund_amount FROM tickets WHERE ticket_id = ?", ("T00097",))
    assert row == ("취소", 0, 88000)
    again = cancel_ticket.func(ticket_id="T00097", runtime=runtime_for(context))
    assert "이미 취소" in again["error"]


def test_goods_refund_inserts_request(make_context):
    """배송완료 7일 안 주문은 반품 배송비를 뺀 환불 요청을 만들고, 출고 전 주문은 거절한다."""
    context = make_context("F0004")
    result = request_goods_refund.func(order_id="O00381", runtime=runtime_for(context))
    assert result["refund_amount"] == 15000
    assert read_one(context.db_path, "SELECT status FROM orders WHERE order_id = ?", ("O00381",))[0] == "환불요청"
    assert read_one(context.db_path, "SELECT status, amount FROM refunds WHERE order_id = ?", ("O00381",)) == ("접수", 15000)
    not_shipped = request_goods_refund.func(order_id="O00400", runtime=runtime_for(context))
    assert "주문 취소" in not_shipped["error"]


def test_my_tickets_reads_login_fan_only(make_context):
    """내 티켓 도구는 로그인한 팬의 티켓만 돌려준다(모델이 fan_id 를 넘길 자리가 없다)."""
    result = get_my_tickets.func(runtime=runtime_for(make_context("F0001")))
    seats = []
    for ticket in result["tickets"]:
        seats.append(ticket["seat"])
    assert seats == ["1층 B구역 7열 12번"]
    assert "fan_id" not in get_my_tickets.tool_call_schema.model_json_schema()["properties"]


def test_empty_lists_come_as_dict(make_context):
    """티켓 0장, 주문 0건인 팬도 빈 목록 대신 키가 있는 dict 를 받는다(도구 결과 내용이 비지 않게)."""
    assert get_my_tickets.func(runtime=runtime_for(make_context("F0002"))) == {"tickets": []}
    assert get_my_orders.func(runtime=runtime_for(make_context("F0003"))) == {"orders": []}


def test_my_profile_has_no_contact(make_context):
    """내 회원 정보 도구는 상담에 쓰지 않는 연락처(전화번호, 이메일)와 주소를 모델에게 넘기지 않는다."""
    profile = get_my_profile.func(runtime=runtime_for(make_context("F0001")))
    assert profile["fan_id"] == "F0001"
    assert "phone" not in profile
    assert "email" not in profile
    assert "address" not in profile


def test_event_venue_geocodes_official_address_only(make_context, fake_nominatim):
    """공연장 도구는 공연 id 의 등록된 공식 공연장 주소만 Nominatim 에 묻고, 찾은 위치를 결과에 담는다."""
    result = get_event_venue.func(event_id="E02", runtime=runtime_for(make_context("F0001")))
    assert result["name"] == "루미너스홀 부산"
    assert result["lat"] == 37.5227
    assert fake_nominatim.requests[0]["params"]["q"] == "부산광역시 해운대구 APEC로 55"
    # 없는 공연 id 면 지오코딩하지 않고 이유를 돌려준다
    assert "error" in get_event_venue.func(event_id="E99", runtime=runtime_for(make_context("F0001")))
    assert len(fake_nominatim.requests) == 1
