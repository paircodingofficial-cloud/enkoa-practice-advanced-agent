"""도구 층: 팬 DB(luna_fan.db)를 읽기 전용으로 조회하는 함수.

함수는 모두 평범한 dict 나 dict 목록을 돌려준다. 누구의 정보를 볼지(fan_id)는 부르는 쪽(그래프, 실행 레일)이 로그인한 팬으로 정한다.
db_path 를 주지 않으면 data/luna_fan.db 를 읽는다. 평가처럼 DB 사본으로 돌릴 때만 사본 경로를 넘긴다.
"""
import sqlite3
from pathlib import Path

from app.core.config import DB_PATH


# [보조 함수] 읽기 전용 연결
def connect(db_path=DB_PATH) -> sqlite3.Connection:
    """DB 를 읽기 전용으로 연 연결을 돌려준다. 행은 열 이름으로 꺼낼 수 있다."""
    # mode=ro: 조회 함수가 실수로 DB 를 고치지 못하게 읽기 전용으로 연다(한글 경로는 as_uri 가 바꿔 준다)
    connection = sqlite3.connect(Path(db_path).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


# [보조 함수] 조회 실행
def fetch_all(query: str, params: tuple = (), db_path=DB_PATH) -> list:
    """쿼리를 실행해 행마다 {열 이름: 값} dict 로 바꾼 목록을 돌려준다(행이 없으면 빈 목록)."""
    # 조회가 실패해도 연결은 닫는다. 값은 ? 자리에 params 로 넣는다(쿼리 글에 이어 붙이지 않는다)
    connection = connect(db_path)
    try:
        rows = connection.execute(query, params).fetchall()
    finally:
        connection.close()

    # sqlite3.Row 는 연결이 닫히면 다루기 불편하므로 평범한 dict 로 바꿔 둔다
    results = []
    for row in rows:
        results.append(dict(row))
    return results


# [도구 함수] 회원 정보
def get_fan(fan_id: str, db_path=DB_PATH) -> dict | None:
    """팬 한 명의 회원 정보(fans 표의 한 행)를 돌려준다. 없는 팬이면 None 이다."""
    rows = fetch_all("SELECT * FROM fans WHERE fan_id = ?", (fan_id,), db_path)

    # 없는 팬 id 면 None, 있으면 그 한 행이다
    if len(rows) == 0:
        return None
    return rows[0]


# [도구 함수] 내 티켓
def get_my_tickets(fan_id: str, db_path=DB_PATH) -> list:
    """팬 본인의 티켓 목록을 공연 이름, 시작 시각, 공연장 이름과 함께 돌려준다."""
    # 티켓 표에는 공연 id 만 있으므로 공연, 공연장 표를 이어 붙여 사람이 읽는 이름을 함께 꺼낸다
    query = """
        SELECT t.ticket_id, t.event_id, e.title, e.starts_at, v.name AS venue_name,
               t.seat, t.grade, t.price, t.status, t.booked_at, t.cancel_deadline,
               t.cancel_fee, t.refund_amount, t.transferred_to
        FROM tickets t
        JOIN events e ON e.event_id = t.event_id
        JOIN venues v ON v.venue_id = e.venue_id
        WHERE t.fan_id = ?
        ORDER BY e.starts_at, t.ticket_id
    """
    return fetch_all(query, (fan_id,), db_path)


# [도구 함수] 내 굿즈 주문
def get_my_orders(fan_id: str, db_path=DB_PATH) -> list:
    """팬 본인의 굿즈 주문 목록을 상품 이름, 환불 상태와 함께 돌려준다."""
    # 환불 신청이 없는 주문도 보여야 하므로 환불 표는 LEFT JOIN 으로 붙인다
    query = """
        SELECT o.order_id, o.product_id, p.name AS product_name, o.qty, o.amount, o.status,
               o.ordered_at, o.shipped_at, o.delivered_at, o.tracking_no,
               r.status AS refund_status, r.amount AS refund_amount
        FROM orders o
        JOIN products p ON p.product_id = o.product_id
        LEFT JOIN refunds r ON r.order_id = o.order_id
        WHERE o.fan_id = ?
        ORDER BY o.ordered_at DESC
    """
    return fetch_all(query, (fan_id,), db_path)


# [도구 함수] 공연 하나
def get_event(event_id: str, db_path=DB_PATH) -> dict | None:
    """공연 하나의 일정, 공연장, 좌석 등급별 가격을 돌려준다. 없으면 None 이다."""
    query = """
        SELECT e.*, v.name AS venue_name, v.address AS venue_address
        FROM events e
        JOIN venues v ON v.venue_id = e.venue_id
        WHERE e.event_id = ?
    """
    rows = fetch_all(query, (event_id,), db_path)

    # 없는 공연 id 면 None 이다
    if len(rows) == 0:
        return None
    event = rows[0]

    # 좌석 등급은 공연마다 여러 줄이라 목록으로 붙인다
    event["seat_grades"] = fetch_all(
        "SELECT grade, price, capacity, area FROM seat_grades WHERE event_id = ? ORDER BY price DESC",
        (event_id,),
        db_path,
    )
    return event


# [도구 함수] 공연 목록
def list_events(db_path=DB_PATH) -> list:
    """모든 공연의 id, 이름, 도시, 시작 시각, 공연장 이름을 시작 순서로 돌려준다."""
    query = """
        SELECT e.event_id, e.title, e.city, e.starts_at, v.name AS venue_name
        FROM events e
        JOIN venues v ON v.venue_id = e.venue_id
        ORDER BY e.starts_at
    """
    return fetch_all(query, (), db_path)


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.tools.fan_db
    print("공연 목록:")
    for event in list_events():
        print("-", event["event_id"], event["title"], event["starts_at"], event["venue_name"])
    fan = get_fan("F0001")
    print("F0001:", fan["nickname"], fan["membership"], fan["role"])
    print("F0001 티켓:", get_my_tickets("F0001"))
    print("F0001 주문 수:", len(get_my_orders("F0001")))
    print("E01 좌석 등급:", get_event("E01")["seat_grades"])
