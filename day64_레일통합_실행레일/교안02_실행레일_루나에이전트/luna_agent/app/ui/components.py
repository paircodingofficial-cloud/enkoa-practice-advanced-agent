"""화면 층: Streamlit 화면 조각(머리, 말풍선, 카드, 지도, 레일 판정 기록)을 그리는 함수.

그래프나 레일을 부르지 않는다. 화면(ui/chat_app.py)이 받은 결과 dict 를 넘기면 그리기만 한다.
스타일은 같은 폴더의 style.css 에 있고 inject_css 가 페이지에 넣는다.
"""
import base64
import html
import re
from pathlib import Path

import pydeck as pdk
import streamlit as st

from app.core.config import AVATAR_PATH

STYLE_PATH = Path(__file__).resolve().parent / "style.css"

# 판정 상태 이름을 화면 글자로 바꾸는 표
STATUS_LABELS = {
    "passed": "통과",
    "modified": "가림",
    "blocked": "막음",
    "info": "안내",
}

# 티켓, 주문 상태 가운데 막힘 색으로 보여 줄 값
NEGATIVE_STATES = ["취소", "환불요청", "환불완료"]


# [보조 함수] 스타일 넣기
def inject_css() -> None:
    """style.css 를 읽어 페이지에 넣는다. 페이지마다 맨 앞에서 한 번 부른다."""
    css = STYLE_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# [보조 함수] 그림을 HTML 에 바로 넣는 주소로
def image_data_uri(path) -> str:
    """PNG 파일을 HTML img 태그에 바로 넣을 수 있는 data 주소 문자열로 돌려준다. 파일이 없으면 빈 문자열이다."""
    path = Path(path)
    # 파일이 없으면 img 태그가 빈 그림을 그리도록 빈 문자열
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# [보조 함수] 글을 HTML 로 안전하게
def to_html_text(text: str) -> str:
    """특수 문자를 HTML 글자로, **굵게** 를 <b> 로, 줄바꿈을 <br> 로 바꾼 문자열을 돌려준다."""
    # 팬이 보낸 글에 태그가 있어도 화면에서 실행되지 않게 먼저 바꾼다
    escaped = html.escape(str(text))
    # 모델이 쓴 마크다운 굵게 표시는 별표가 그대로 보이지 않게 굵은 글씨로 바꾼다(말풍선은 HTML 이라 마크다운을 그리지 않는다)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    return escaped.replace("\n", "<br>")


# [보조 함수] 색 있는 작은 표시
def badge_html(color: str, label: str) -> str:
    """색 이름(passed, modified, blocked, info)과 글자로 작은 표시 HTML 을 돌려준다."""
    return f'<span class="luna-status {html.escape(color)}">{to_html_text(label)}</span>'


# [보조 함수] 판정 상태 표시
def status_badge(status: str) -> str:
    """판정 상태(passed, modified, blocked, info)를 한국어 글자 표시 HTML 로 돌려준다."""
    label = STATUS_LABELS.get(status, status)
    return badge_html(status, label)


# [보조 함수] 카드 안 칸 하나
def field_html(label: str, value) -> str:
    """카드 안의 '이름: 값' 한 칸 HTML 을 돌려준다. 값이 비면 '-' 로 보여 준다."""
    shown = value
    if value is None or value == "":
        shown = "-"
    return (
        f'<div><div class="luna-field-label">{to_html_text(label)}</div>'
        f'<div class="luna-field-value">{to_html_text(shown)}</div></div>'
    )


# [보조 함수] 금액 글자
def won(amount) -> str:
    """금액을 '110,000원' 꼴 문자열로 돌려준다. 값이 없으면 빈 문자열이다."""
    # 금액이 없는 칸(환불 전 주문 등)은 비워 둔다
    if amount is None:
        return ""
    return f"{int(amount):,}원"


# [화면] 머리
def render_header(profile: dict | None) -> None:
    """루나 얼굴, 이름, 로그인한 팬의 닉네임과 등급을 머리에 그린다. profile 은 get_fan 결과다."""
    avatar = image_data_uri(AVATAR_PATH)

    # 로그인한 팬이 있으면 닉네임과 등급을 오른쪽 표시로 보여 준다
    chips = ""
    if profile is not None:
        chips = f'<span class="luna-chip">{to_html_text(profile["nickname"])}</span>'
        chips += f'<span class="luna-chip muted">{to_html_text(profile["membership"])}</span>'
        # 운영팀 계정은 표시를 하나 더 붙인다
        if profile.get("role") == "staff":
            chips += '<span class="luna-chip muted">운영팀</span>'

    st.markdown(
        f"""<div class="luna-header">
<img src="{avatar}" alt="루나">
<div class="luna-header-text">
<p class="luna-header-title">루나</p>
<div class="luna-header-sub">루미너스 엔터테인먼트 버추얼 아이돌, 팬 서비스 상담</div>
</div>
<div class="luna-chip-row">{chips}</div>
</div>""",
        unsafe_allow_html=True,
    )


# [화면] 말풍선
def render_message(role: str, text: str) -> None:
    """대화 한 줄을 말풍선으로 그린다. role 은 'user'(팬) 또는 'assistant'(루나)다."""
    # 팬 말풍선은 오른쪽에 얼굴 없이 그리고 끝낸다
    if role == "user":
        st.markdown(
            f'<div class="luna-row user"><div class="luna-bubble user">{to_html_text(text)}</div></div>',
            unsafe_allow_html=True,
        )
        return

    # 루나 말풍선은 왼쪽에 얼굴을 붙인다
    avatar = image_data_uri(AVATAR_PATH)
    st.markdown(
        f'<div class="luna-row"><img class="luna-avatar" src="{avatar}" alt="루나">'
        f'<div class="luna-bubble assistant">{to_html_text(text)}</div></div>',
        unsafe_allow_html=True,
    )


# [보조 함수] 판정 기록 한 줄
def trace_row_html(stage: str, result) -> str:
    """판정 기록 한 단계(이름, 결과)를 한 줄 HTML 로 돌려준다."""
    # 결과가 문자열이면 안내로 보여 준다(예: 사람 승인 대기, 사람이 거절함)
    if not isinstance(result, dict):
        return (
            f'<div class="luna-trace-row"><div class="luna-trace-stage">{to_html_text(stage)}</div>'
            f'{status_badge("info")}<div class="luna-trace-detail">{to_html_text(result)}</div></div>'
        )

    # 결과 dict 에서 막은 흐름, 규칙 id, 설명을 이어 한 줄로 만든다
    parts = []
    if result.get("blocked_by"):
        parts.append(result["blocked_by"])
    if result.get("rule_id"):
        parts.append("규칙 " + result["rule_id"])
    if result.get("detail"):
        parts.append(str(result["detail"]))
    detail = ", ".join(parts)
    status = result.get("status", "info")
    return (
        f'<div class="luna-trace-row"><div class="luna-trace-stage">{to_html_text(stage)}</div>'
        f'{status_badge(status)}<div class="luna-trace-detail">{to_html_text(detail)}</div></div>'
    )


# [화면] 레일 판정 기록
def render_rail_trace(trace: dict) -> None:
    """레일 판정 기록을 접이식 상자로 그린다. trace 는 {단계 이름: 결과 dict 또는 문자열} 이다."""
    # 결과 dict 는 status(passed, modified, blocked), blocked_by, rule_id, detail 키를 읽는다
    rows = []
    for stage, result in trace.items():
        rows.append(trace_row_html(stage, result))
    with st.expander("레일 판정 기록", expanded=False):
        st.markdown("".join(rows), unsafe_allow_html=True)


# [화면] 티켓 카드
def render_ticket_card(ticket: dict) -> None:
    """티켓 한 장(get_my_tickets 의 한 행)을 카드로 그린다."""
    # 취소된 티켓은 막힘 색, 나머지는 통과 색으로 상태를 보여 준다
    color = "passed"
    if ticket["status"] in NEGATIVE_STATES:
        color = "blocked"
    fields = [
        field_html("좌석", ticket["seat"]),
        field_html("등급", ticket["grade"]),
        field_html("가격", won(ticket["price"])),
        field_html("취소 마감", ticket["cancel_deadline"]),
    ]
    st.markdown(
        f"""<div class="luna-card">
<div class="luna-card-title">{to_html_text(ticket["title"])} {badge_html(color, ticket["status"])}</div>
<div class="luna-card-sub">{to_html_text(ticket["starts_at"])}, {to_html_text(ticket["venue_name"])}</div>
<div class="luna-card-grid">{"".join(fields)}</div>
</div>""",
        unsafe_allow_html=True,
    )


# [화면] 주문 카드
def render_order_card(order: dict) -> None:
    """굿즈 주문 하나(get_my_orders 의 한 행)를 카드로 그린다."""
    # 환불 중이거나 끝난 주문은 막힘 색으로 보여 준다
    color = "passed"
    if order["status"] in NEGATIVE_STATES:
        color = "blocked"
    fields = [
        field_html("수량", order["qty"]),
        field_html("결제 금액", won(order["amount"])),
        field_html("주문 시각", order["ordered_at"]),
        field_html("송장 번호", order["tracking_no"]),
    ]
    # 환불 신청이 있으면 환불 상태 칸을 더한다
    if order.get("refund_status"):
        fields.append(field_html("환불 상태", order["refund_status"]))
    st.markdown(
        f"""<div class="luna-card">
<div class="luna-card-title">{to_html_text(order["product_name"])} {badge_html(color, order["status"])}</div>
<div class="luna-card-sub">주문 번호 {to_html_text(order["order_id"])}</div>
<div class="luna-card-grid">{"".join(fields)}</div>
</div>""",
        unsafe_allow_html=True,
    )


# [화면] 공연장 지도 카드
def render_map_card(venue: dict) -> None:
    """공연장 이름, 주소 카드와 위치 지도(pydeck)를 그린다. venue 는 get_venue_for_event 결과다."""
    st.markdown(
        f"""<div class="luna-card">
<div class="luna-card-title">{to_html_text(venue["name"])}</div>
<div class="luna-card-sub">{to_html_text(venue["address"])}</div>
<div class="luna-card-sub" style="margin-top:6px">{to_html_text(venue.get("note", ""))}</div>
</div>""",
        unsafe_allow_html=True,
    )

    # 지도 서비스(Nominatim)에서 위치를 못 찾았으면 카드만 보여 주고 지도는 그리지 않는다
    if venue["lat"] is None:
        return

    # 공연장 한 점을 라벤더색 원으로 찍는다
    point = [{"name": venue["name"], "lat": venue["lat"], "lon": venue["lon"]}]
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=point,
        get_position="[lon, lat]",
        get_fill_color=[139, 127, 214, 200],
        get_radius=120,
        pickable=True,
    )
    view = pdk.ViewState(latitude=venue["lat"], longitude=venue["lon"], zoom=14)
    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        map_provider="carto",
        map_style="light",
        tooltip={"text": "{name}"},
    )
    st.pydeck_chart(deck, height=260)


# [화면] 막힘 카드
def render_blocked_card(rule_id: str, message: str) -> None:
    """레일이 막은 요청을 안내 문장과 막은 규칙 id 가 든 카드로 그린다."""
    rule_text = ""
    # 규칙 id 가 있을 때만 카드 아래에 적는다
    if rule_id:
        rule_text = f'<div class="luna-card-sub" style="margin-top:6px">막은 규칙 {to_html_text(rule_id)}</div>'
    st.markdown(
        f"""<div class="luna-card blocked">
<div class="luna-card-title">{status_badge("blocked")} 요청을 처리하지 않았어요</div>
<div style="margin-top:6px">{to_html_text(message)}</div>
{rule_text}
</div>""",
        unsafe_allow_html=True,
    )


# [화면] 팬아트 카드
def render_fanart_card(path, verdicts: dict, remaining: int) -> None:
    """만든 팬아트 그림, 검사 결과 표시, 오늘 남은 횟수를 카드로 그린다. verdicts 는 {검사 이름: 상태} 다."""
    # 검사마다 통과, 막음 표시를 한 줄로 잇는다
    badges = []
    for name, status in verdicts.items():
        badges.append(f"{to_html_text(name)} {status_badge(status)}")
    st.markdown(
        f"""<div class="luna-card">
<div class="luna-card-title">AI 생성 팬아트</div>
<div class="luna-card-sub">{"&nbsp;&nbsp;".join(badges)}</div>
<div class="luna-card-sub" style="margin-top:6px">오늘 남은 횟수 {int(remaining)}회</div>
</div>""",
        unsafe_allow_html=True,
    )

    # 그림 파일이 있을 때만 보여 준다(막힌 그림은 저장하지 않는다)
    if path is not None and Path(path).exists():
        st.image(str(path), width=360)


# [화면] 승인 대기 카드
def render_approval_card(title: str, details: dict, key: str) -> str | None:
    """사람 승인이 필요한 작업 카드를 그리고, 누른 버튼에 따라 'approve', 'reject', 누르지 않았으면 None 을 돌려준다."""
    fields = []
    for label, value in details.items():
        fields.append(field_html(label, value))
    st.markdown(
        f"""<div class="luna-card approval">
<div class="luna-card-title">{status_badge("info")} {to_html_text(title)}</div>
<div class="luna-card-sub">실행하기 전에 내용을 확인해 주세요.</div>
<div class="luna-card-grid">{"".join(fields)}</div>
</div>""",
        unsafe_allow_html=True,
    )

    # 버튼 두 개를 나란히 둔다. key 로 카드마다 버튼을 구분한다
    left, right, _ = st.columns([1, 1, 3])
    # 누른 버튼의 결정을 돌려준다. 이번 실행에서 아무것도 누르지 않았으면 None
    if left.button("승인", key=f"{key}_approve", type="primary"):
        return "approve"
    if right.button("거절", key=f"{key}_reject"):
        return "reject"
    return None


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.ui.components
    # 화면을 띄우지 않고 HTML 조각만 만들어 본다. 화면은 uv run python -m streamlit run app/ui/chat_app.py 로 본다
    print("스타일 파일 있음:", STYLE_PATH.exists(), "/ 루나 얼굴 그림 있음:", AVATAR_PATH.exists())
    print("상태 표시:", status_badge("blocked"))
    print("칸 하나:", field_html("가격", won(110000)))
    print("판정 기록 한 줄:", trace_row_html("입력 레일", {"status": "blocked", "blocked_by": "jev policy input", "rule_id": "IN-05"}))
