"""도구 층: 에이전트에게 붙이는 예매, 주문, 회원, 규정 검색, 공연장 도구.

- 누구의 정보인지(fan_id)는 모델이 정하지 않는다. 도구가 로그인 정보(runtime.context.fan_id)에서 읽는다.
  runtime 은 ToolRuntime[AgentContext] 로 적는다. [AgentContext] 를 빼면 pydantic 이 context 칸을 None 으로 알아 도구를 부를 때마다 직렬화 경고를 낸다.
- 티켓 번호, 주문 번호처럼 모델이 넘기는 값의 주인 확인은 도구 밖의 실행 레일(guards/execution.py)이 실행 전에 한다.
- 쓰기 도구(change_seat, cancel_ticket, request_goods_refund)는 runtime.context.db_path 의 DB 를 고친다.
  앱은 data/luna_fan.db 를, 평가(evaluate.py)는 케이스마다 만든 임시 사본을 넘기므로 평가를 여러 번 돌려도 원본이 바뀌지 않는다.
- 날짜 계산의 '지금'은 수업 데이터의 기준 시각(config.BASE_DATETIME)이다.
- 도구는 늘 dict 를 돌려준다. 업무 규칙으로 거절하면 {"error": 이유} 를 돌려주고, 평가와 화면은 이것을 '거절(rejected)'로 읽는다.
  목록을 그대로 돌려주면 빈 목록([])일 때 langchain 이 도구 결과 내용을 비워 버려 화면과 모델이 읽을 글이 없어진다.
"""
import re
import sqlite3
from datetime import datetime

from langchain.tools import ToolRuntime, tool

from app.core.config import BASE_DATETIME, settings
from app.core.schemas import AgentContext
# 도구 이름(get_my_tickets 등)이 fan_db 의 조회 함수 이름과 같아서, 조회 함수는 fan_db.이름 으로 부른다
from app.tools import fan_db
from app.tools.retriever import format_documents, get_vector_store
from app.tools.venue import get_venue_for_event

# 굿즈 단순 변심 환불 규정(knowledge 굿즈_주문.md 의 gds-02)
REFUND_WINDOW_DAYS = 7       # 받은 날을 포함해 7일 안
RETURN_SHIPPING_FEE = 3000   # 단순 변심 반품 배송비는 환불 금액에서 뺀다

# 좌석 "1층 A구역 3열 5번" 과 등급 구역 "1층 A구역 1~10열 1~20번" 의 모양
SEAT_PATTERN = re.compile(r"^(\d+층) ([A-Z])구역 (\d+)열 (\d+)번$")
AREA_PATTERN = re.compile(r"(\d+층) ([A-Z])구역 (\d+)~(\d+)열 (\d+)~(\d+)번")


# [보조 함수] 티켓 하나
def find_ticket(ticket_id: str, db_path) -> dict | None:
    """티켓 한 장의 행을 dict 로 돌려준다. 없으면 None 이다."""
    rows = fan_db.fetch_all("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,), db_path)
    # 없는 번호: 호출한 쪽(실행 레일, 도구)이 None 을 보고 이유를 정한다
    if len(rows) == 0:
        return None
    return rows[0]


# [보조 함수] 주문 하나
def find_order(order_id: str, db_path) -> dict | None:
    """주문 하나를 상품 이름, 환불 가능 여부, 환불 신청 상태와 함께 dict 로 돌려준다. 없으면 None 이다."""
    query = """
        SELECT o.*, p.name AS product_name, p.refundable, r.refund_id
        FROM orders o
        JOIN products p ON p.product_id = o.product_id
        LEFT JOIN refunds r ON r.order_id = o.order_id
        WHERE o.order_id = ?
    """
    rows = fan_db.fetch_all(query, (order_id,), db_path)
    # 없는 번호
    if len(rows) == 0:
        return None
    return rows[0]


# [보조 함수] 다음 id
def next_id(db_path, table: str, column: str, prefix: str) -> str:
    """표에서 가장 큰 id 의 다음 번호(예: R0025 -> R0026)를 돌려준다."""
    rows = fan_db.fetch_all(f"SELECT MAX({column}) AS last_id FROM {table}", (), db_path)
    number = 0
    # 표가 비어 있으면 0 에서 시작해 첫 id 가 0001 이 된다
    if rows[0]["last_id"] is not None:
        number = int(rows[0]["last_id"][len(prefix):])
    return f"{prefix}{number + 1:04d}"


# [보조 함수] 좌석이 등급 구역 안인가
def seat_in_area(seat: str, area_text: str) -> bool:
    """좌석이 등급 구역(예: '1층 A구역 1~10열 1~20번, ...') 안에 있으면 True 를 돌려준다."""
    seat_match = SEAT_PATTERN.match(seat)
    # 좌석 모양이 아니면 어느 구역에도 들지 않는다
    if seat_match is None:
        return False
    floor, block, row, number = seat_match.group(1), seat_match.group(2), int(seat_match.group(3)), int(seat_match.group(4))

    # 구역 글은 쉼표로 여러 구역을 잇는다. 하나라도 맞으면 그 등급 좌석이다
    for area in AREA_PATTERN.findall(area_text):
        # 층이나 구역 글자가 다르면 다음 구역을 본다
        if area[0] != floor or area[1] != block:
            continue
        # 열과 번호가 범위 안이면 이 등급 좌석이다
        if int(area[2]) <= row <= int(area[3]) and int(area[4]) <= number <= int(area[5]):
            return True
    # 맞는 구역이 없음
    return False


# [보조 함수] 티켓 취소 견적
def cancel_quote(ticket: dict, db_path) -> dict:
    """티켓을 지금 취소할 때의 {"fee": 수수료, "refund": 돌려받을 금액, "error": 취소할 수 없는 이유(취소할 수 있으면 빈 문자열)} 를 돌려준다."""
    # 이미 취소된 티켓
    if ticket["status"] != "예매":
        return {"fee": 0, "refund": 0, "error": f"이미 {ticket['status']}된 티켓이에요."}

    # 공연 전날 오후 5시(cancel_deadline)가 지나면 취소할 수 없다(tkt-06)
    now = datetime.fromisoformat(BASE_DATETIME)
    if now >= datetime.fromisoformat(ticket["cancel_deadline"]):
        return {"fee": 0, "refund": 0, "error": f"취소 마감({ticket['cancel_deadline']})이 지나 취소할 수 없어요."}

    # 공연일까지 남은 날로 수수료 비율을 정한다(10일 전까지 0%, 9~7일 전 10%, 6~3일 전 20%, 그 뒤 30%)
    event = fan_db.get_event(ticket["event_id"], db_path)
    days_before = (datetime.fromisoformat(event["starts_at"]).date() - now.date()).days
    # 가까운 날부터 먼 날 순으로 덮어써, 남은 날에 맞는 가장 낮은 비율이 남는다
    rate = 0.3
    if days_before >= 3:
        rate = 0.2
    if days_before >= 7:
        rate = 0.1
    if days_before >= 10:
        rate = 0.0
    fee = int(ticket["price"] * rate)
    return {"fee": fee, "refund": ticket["price"] - fee, "error": ""}


# [보조 함수] 굿즈 환불 견적
def refund_quote(order: dict) -> dict:
    """주문을 지금 단순 변심으로 환불할 때의 {"amount": 환불 예정 금액, "error": 환불할 수 없는 이유(할 수 있으면 빈 문자열)} 를 돌려준다."""
    # 출고 전 주문은 환불이 아니라 주문 취소로 처리한다(gds-05)
    if order["status"] == "결제완료":
        return {"amount": 0, "error": "출고 전 주문은 [주문 내역 > 주문 취소]에서 수수료 없이 바로 취소돼요."}
    # 배송 중처럼 아직 받지 않은 주문
    if order["status"] != "배송완료":
        return {"amount": 0, "error": f"{order['status']} 상태라 아직 환불을 요청할 수 없어요."}
    # 환불 신청 행이 이미 있는 주문
    if order["refund_id"] is not None:
        return {"amount": 0, "error": "이미 환불을 요청한 주문이에요."}
    # 주문 제작 상품(refundable = 0)
    if order["refundable"] == 0:
        return {"amount": 0, "error": "주문 제작 상품이라 단순 변심 환불이 안 돼요."}

    # 받은 날을 포함해 7일 안이어야 한다: 받은 날이 0일째이므로 6일 차이까지 허용한다
    now = datetime.fromisoformat(BASE_DATETIME)
    days_since = (now.date() - datetime.fromisoformat(order["delivered_at"]).date()).days
    if days_since >= REFUND_WINDOW_DAYS:
        return {"amount": 0, "error": "받은 날을 포함해 7일이 지나 단순 변심 환불이 안 돼요."}
    # 환불할 수 있음: 결제 금액에서 반품 배송비를 뺀다
    return {"amount": order["amount"] - RETURN_SHIPPING_FEE, "error": ""}


# [도구] 내 회원 정보
@tool
def get_my_profile(runtime: ToolRuntime[AgentContext]) -> dict:
    """로그인한 팬 본인의 회원 정보(닉네임, 회원 등급, 팬클럽 가입일)를 돌려준다."""
    fan = fan_db.get_fan(runtime.context.fan_id, runtime.context.db_path)
    # 집 주소, 전화번호, 이메일은 상담에 필요 없어 모델에게 넘기지 않는다
    return {
        "fan_id": fan["fan_id"], "nickname": fan["nickname"], "membership": fan["membership"],
        "membership_since": fan["membership_since"], "joined_at": fan["joined_at"],
    }


# [도구] 내 티켓
@tool
def get_my_tickets(runtime: ToolRuntime[AgentContext]) -> dict:
    """로그인한 팬 본인의 티켓 목록(티켓 번호, 공연, 좌석, 등급, 상태, 취소 마감)을 {"tickets": [...]} 로 돌려준다."""
    return {"tickets": fan_db.get_my_tickets(runtime.context.fan_id, runtime.context.db_path)}


# [도구] 내 굿즈 주문
@tool
def get_my_orders(runtime: ToolRuntime[AgentContext]) -> dict:
    """로그인한 팬 본인의 굿즈 주문 목록(주문 번호, 상품, 상태, 배송 날짜, 환불 상태)을 {"orders": [...]} 로 돌려준다."""
    return {"orders": fan_db.get_my_orders(runtime.context.fan_id, runtime.context.db_path)}


# [도구] 회원 조회(운영팀 전용)
@tool
def lookup_fan(fan_id: str, runtime: ToolRuntime[AgentContext]) -> dict:
    """운영팀 전용: 회원 id 로 그 회원의 정보(닉네임, 등급, 연락처, 이메일)를 돌려준다."""
    fan = fan_db.get_fan(fan_id, runtime.context.db_path)
    # 없는 회원 id: 업무 규칙 거절
    if fan is None:
        return {"error": "없는 회원 id 예요."}
    # 연락처가 든 결과다. 모델이 읽기 전에 실행 레일(mask_member_info)이 가린다
    return {
        "fan_id": fan["fan_id"], "nickname": fan["nickname"], "membership": fan["membership"],
        "phone": fan["phone"], "email": fan["email"], "role": fan["role"],
    }


# [도구] 규정 검색
# content_and_artifact: (모델이 읽을 문자열, 검색 문서 목록)을 돌려준다
# 문서 목록은 ToolMessage.artifact 에 담겨 모델에게 가지 않고, 실행 후 검사(check_tool_result)가 문서 단위로 읽는다
@tool(response_format="content_and_artifact")
def search_policy(query: str):
    """루나 공지와 규정(티켓, 굿즈, 팬클럽, 이용 정책) 문서에서 질문과 관련된 절을 찾아 돌려준다."""
    # 저장소는 준비 단계에서 만들어 둔다(uv run -m app.tools.retriever --build). 여기서는 열어서 검색만 한다
    docs = get_vector_store().similarity_search(query, k=settings.retriever_k)
    return format_documents(docs), docs


# [도구] 공연장 위치
@tool
def get_event_venue(event_id: str, runtime: ToolRuntime[AgentContext]) -> dict:
    """공연 id(예: E01)로 공연장 이름, 주소, 위도, 경도, 찾아가는 길 안내를 돌려준다."""
    # 위치는 DB 에 등록된 공식 공연장 주소로만 찾는다(tools/venue.py 가 Nominatim 에 묻는다). 인자는 공연 id 뿐이라 임의 주소를 넘길 자리가 없다
    venue = get_venue_for_event(event_id, runtime.context.db_path)
    # 없는 공연 id: 실행 레일이 먼저 막지만, 도구만 따로 불러도 안전하게 이유를 돌려준다
    if venue is None:
        return {"error": "없는 공연 id 예요."}
    return venue


# [도구] 좌석 변경
@tool
def change_seat(ticket_id: str, new_seat: str, runtime: ToolRuntime[AgentContext]) -> dict:
    """티켓 좌석을 같은 공연, 같은 등급의 빈 좌석(예: '1층 A구역 3열 5번')으로 바꾸고 결과를 돌려준다."""
    db_path = runtime.context.db_path
    ticket = find_ticket(ticket_id, db_path)
    # 없는 티켓, 이미 취소된 티켓: 바꿀 좌석이 없다
    if ticket is None:
        return {"error": "없는 티켓 번호예요."}
    if ticket["status"] != "예매":
        return {"error": f"{ticket['status']}된 티켓은 좌석을 바꿀 수 없어요."}

    # 1. 좌석 변경 마감(공연 7일 전 23시 59분)을 확인한다(tkt-07)
    event = fan_db.get_event(ticket["event_id"], db_path)
    if datetime.fromisoformat(BASE_DATETIME) > datetime.fromisoformat(event["seat_change_deadline"]):
        return {"error": f"좌석 변경 마감({event['seat_change_deadline']})이 지났어요."}

    # 2. 새 좌석이 같은 등급의 구역 안인지 확인한다
    area_text = ""
    for grade in event["seat_grades"]:
        # 이 티켓 등급의 구역 글을 찾는다
        if grade["grade"] == ticket["grade"]:
            area_text = grade["area"]
    if not seat_in_area(new_seat, area_text):
        return {"error": f"{new_seat} 은 {ticket['grade']} 구역({area_text})의 좌석이 아니에요."}

    # 3. 다른 사람이 이미 예매한 좌석인지 확인한다. 이미 팔린 좌석은 어떤 요청이 와도 빼앗지 않는다
    taken = fan_db.fetch_all("SELECT ticket_id FROM tickets WHERE event_id = ? AND seat = ? AND status = '예매'",
                      (ticket["event_id"], new_seat), db_path)
    if len(taken) > 0:
        return {"error": f"{new_seat} 은 이미 예매된 좌석이에요."}

    # 4. 좌석을 바꿔 저장한다
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("UPDATE tickets SET seat = ? WHERE ticket_id = ?", (new_seat, ticket_id))
        connection.commit()
    finally:
        connection.close()
    return {"ticket_id": ticket_id, "old_seat": ticket["seat"], "new_seat": new_seat, "result": "좌석 변경 완료"}


# [도구] 티켓 취소(위험도 높음: DB 를 바꾸는 실행은 사람 승인 뒤에만 된다. 거절될 호출은 묻지 않고 도구가 이유를 돌려준다)
@tool
def cancel_ticket(ticket_id: str, runtime: ToolRuntime[AgentContext]) -> dict:
    """티켓 예매를 취소하고 수수료와 돌려받을 금액을 돌려준다."""
    db_path = runtime.context.db_path
    ticket = find_ticket(ticket_id, db_path)
    if ticket is None:
        return {"error": "없는 티켓 번호예요."}
    # 이미 취소, 마감 지남: 견적의 이유를 그대로 돌려주고 DB 는 고치지 않는다
    quote = cancel_quote(ticket, db_path)
    if quote["error"]:
        return {"error": quote["error"]}

    # 취소 상태, 취소 시각, 수수료, 환불 금액을 함께 적는다(DB 규칙: 환불 금액 = 가격 - 수수료)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "UPDATE tickets SET status = '취소', cancelled_at = ?, cancel_fee = ?, refund_amount = ? WHERE ticket_id = ?",
            (BASE_DATETIME, quote["fee"], quote["refund"], ticket_id),
        )
        connection.commit()
    finally:
        connection.close()
    return {"ticket_id": ticket_id, "cancel_fee": quote["fee"], "refund_amount": quote["refund"], "result": "예매 취소 완료"}


# [도구] 굿즈 환불 요청(위험도 높음: DB 를 바꾸는 실행은 사람 승인 뒤에만 된다. 거절될 호출은 묻지 않고 도구가 이유를 돌려준다)
@tool
def request_goods_refund(order_id: str, runtime: ToolRuntime[AgentContext]) -> dict:
    """뜯지 않은 굿즈 주문의 단순 변심 환불을 요청하고 환불 예정 금액을 돌려준다."""
    db_path = runtime.context.db_path
    order = find_order(order_id, db_path)
    if order is None:
        return {"error": "없는 주문 번호예요."}
    # 환불할 수 없는 주문: 견적의 이유를 그대로 돌려주고 DB 는 고치지 않는다
    quote = refund_quote(order)
    if quote["error"]:
        return {"error": quote["error"]}

    # 환불 신청 행을 만들고 주문 상태를 '환불요청'으로 바꾼다(gds-05)
    refund_id = next_id(db_path, "refunds", "refund_id", "R")
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO refunds (refund_id, order_id, fan_id, reason, requested_at, status, amount) VALUES (?, ?, ?, ?, ?, '접수', ?)",
            (refund_id, order_id, order["fan_id"], "단순 변심", BASE_DATETIME, quote["amount"]),
        )
        connection.execute("UPDATE orders SET status = '환불요청' WHERE order_id = ?", (order_id,))
        connection.commit()
    finally:
        connection.close()
    return {"order_id": order_id, "refund_id": refund_id, "refund_amount": quote["amount"], "result": "환불 요청 접수"}


# 에이전트에 붙이는 도구(팬아트 도구 create_fanart 는 tools/fanart.py 에 있다)
BOOKING_TOOLS = [
    get_my_profile, get_my_tickets, get_my_orders, lookup_fan, search_policy,
    get_event_venue, change_seat, cancel_ticket, request_goods_refund,
]


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.tools.booking_tools
    # 원본 DB 를 고치지 않도록 읽기와 견적만 확인한다(쓰기는 tests/test_tools.py 가 임시 사본으로 확인한다)
    from app.core.config import DB_PATH

    print("기준 시각:", BASE_DATETIME)
    print("도구:", [each_tool.name for each_tool in BOOKING_TOOLS])
    print("T00097 취소 견적:", cancel_quote(find_ticket("T00097", DB_PATH), DB_PATH))
    print("O00381 환불 견적:", refund_quote(find_order("O00381", DB_PATH)))
    print("O00400 환불 견적:", refund_quote(find_order("O00400", DB_PATH)))
    print("좌석 구역 확인:", seat_in_area("1층 A구역 3열 5번", "1층 A구역 1~10열 1~20번"), seat_in_area("1층 B구역 3열 5번", "1층 A구역 1~10열 1~20번"))
    print("다음 환불 id:", next_id(DB_PATH, "refunds", "refund_id", "R"))
