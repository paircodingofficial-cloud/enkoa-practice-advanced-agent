"""가드 층: 실행 레일. 모델이 도구 호출을 정한 뒤, 도구를 실제로 실행하기 바로 전과 바로 후에 도는 검사.

에이전트 노드(graph/builder.py 의 build_agent)에 붙는 미들웨어다. 표의 순서는 MIDDLEWARE 순서(1~9번)와 같다.
입력, 출력 레일은 여기 없다. 바깥 그래프의 노드(graph/nodes.py)가 요청마다 한 번 돈다.

| 미들웨어 | 자리 | 하는 일 |
|---|---|---|
| expose_tools_by_role | 모델 호출마다(@wrap_model_call) | 역할에 허용된 도구만 모델에게 보여 준다 |
| check_tool_permission | 도구 실행 전(@wrap_tool_call) | 역할, 티켓과 주문의 주인, DB 에 있는 공연 id 인지 확인한다 |
| fanart_quota_and_policy | 팬아트 생성 전 | 한 메시지 한 장, 하루 한도, 그림 요청 정책(Jev)을 본다. 막으면 그림 API 를 부르지 않는다 |
| check_fanart_image | 팬아트 생성 후 | 모더레이션, 브랜드 검사, 워터마크, 요청 기록. 막은 그림은 보여 주지 않고 blocked 폴더에 남긴다 |
| check_tool_result | 도구 실행 후 | 규정 검색 결과에서 숨은 지시가 든 절을 뺀다 |
| mask_member_info | 도구 실행 후 | 회원 정보 도구 결과의 전화번호, 이메일을 모델이 읽기 전에 가린다 |
| approval_mw | 모델이 도구를 고른 직후 | 티켓 취소, 굿즈 환불은 사람 승인 전까지 멈춘다(HumanInTheLoopMiddleware) |
| pii_mws | 모델 호출 뒤 | 답변의 전화번호, 이메일을 끝 몇 자리만 남기고 가린다(PIIMiddleware) |

막을 때는 도구 대신 status="error" 인 도구 결과(ToolMessage)를 돌려준다.
response_metadata 에 막은 미들웨어 이름(rail)과 규칙 id(rule_id)를 남겨 화면과 평가가 읽는다(모델에게는 가지 않는다).
판정 API(그림 요청 Jev, 모더레이션, 브랜드 검사)가 오류를 내면 통과시키지 않고 RAIL-ERROR 로 막는다(fail-closed).

사람 승인은 도구 실행 전 검사보다 앞(모델 호출 직후, after_model 훅)에 돈다. 그래서 승인을 물을지 정할 때 권한과 업무 규칙을 먼저 본다(should_ask_approval).
멈춘 실행은 바깥 그래프의 체크포인터에 대화 ID 별로 저장되고, graph/chat.py 의 resume_turn 이 사람의 결정을 바깥 그래프에 넘겨 이어 간다.
"""
from pathlib import Path

from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    PIIMiddleware,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import ToolMessage

from app.core.config import APPROVAL_TOOLS, MEMBER_INFO_TOOLS, ROLE_TOOLS
from app.core.policies import RAIL_ERROR_RULE, VISUAL, reply_for_rule
from app.core.prompts import IMAGE_REQUEST_POLICY
from app.guards.image_guards import brand_check, moderate_image, stamp_watermark
from app.guards.judges import jev_policy_judgement
from app.guards.validators import PHONE_PATTERN, has_hidden_instruction, mask_pii
from app.tools import fan_db
from app.tools.booking_tools import cancel_quote, find_order, find_ticket, refund_quote
from app.tools.fanart import count_today_fanarts, record_fanart_request
from app.tools.retriever import format_documents

# 실행 레일이 막을 때 남기는 규칙 id. persona.yaml 입력 정책과 같은 뜻이면 그 id 를 쓴다
ROLE_RULE = "IN-04"      # 운영팀 권한을 말로 주장하거나 역할 밖 도구를 씀
OWNER_RULE = "IN-05"     # 다른 팬의 티켓, 주문
VENUE_RULE = "IN-07"     # 공연장이 아닌 곳의 위치
QUOTA_RULE = "IMG-LIMIT"  # 팬아트 하루 한도(visual.yaml generation.daily_limit)
FANART_RUN_RULE = "IMG-RUN"  # 팬 메시지 한 번에 팬아트 한 장(그림 한 장마다 비용이 든다)
LETTER_LENGTH_RULE = "LTR-01"   # 팬레터 글자 수(빈 글, FAN_LETTER_MAX_CHARS 초과). 함께 따라하기에서 쓴다
LETTER_CONTENT_RULE = "LTR-02"  # 팬레터 속 링크, 연락처. 함께 따라하기에서 쓴다

# Jev 가 막은 금지 주제 하나를 고르는 후보 {IMG-01: "[범주] 설명"}. 고객 안내문 생성기와 같은 표(forbidden_content)에서 만든다
IMAGE_RULES = {}
for forbidden in VISUAL["forbidden_content"]:
    IMAGE_RULES[forbidden["id"]] = f"[{forbidden['category']}] {forbidden['description']}"

# 그림 요청 정책 위반 확률이 이 값보다 크면 막는다. 입력, 출력 레일(rails/guard/rails.co)의 Jev 정책 기준값과 같은 0.5 다
# 팬아트 검사는 NeMo 가 아니라 도구 반복 안의 미들웨어가 하므로 기준값도 이 파일에 둔다
IMAGE_POLICY_THRESHOLD = 0.5


# [보조 함수] 막은 도구 결과
def blocked_tool_message(tool_call: dict, rail: str, rule_id: str, reason: str) -> ToolMessage:
    """도구를 실행하지 않고 돌려줄 오류 도구 결과(ToolMessage, status="error")를 돌려준다. 같은 호출 id 를 써야 모델이 어느 호출의 결과인지 안다."""
    # content 는 모델이 읽고 팬에게 전할 이유, response_metadata 는 화면과 평가가 읽는 표시(모델에게는 가지 않는다)
    return ToolMessage(
        content=reason, tool_call_id=tool_call["id"], name=tool_call["name"], status="error",
        response_metadata={"rail": rail, "rule_id": rule_id},
    )


# [보조 함수] 권한 문제 찾기
def permission_problem(tool_call: dict, context) -> dict:
    """도구 호출을 로그인 정보로 확인한 {"rule_id": 막은 규칙 id, "reason": 팬에게 전할 이유} 를 돌려준다. 허락되면 두 칸 모두 빈 문자열이다.

    실행 전 권한 확인(check_tool_permission)과 승인을 물을지 정하는 should_ask_approval 이 같은 판정을 쓴다.
    """
    name = tool_call["name"]
    args = tool_call["args"]

    # 1. 역할 확인: 역할별 도구 노출과 같은 표로 다시 본다. 숨긴 도구 이름을 모델이 지어내 불러도 여기서 걸린다
    if name not in ROLE_TOOLS[context.role]:
        return {"rule_id": ROLE_RULE, "reason": "로그인한 계정의 역할로는 쓸 수 없는 도구예요."}

    # 2. 주인 확인: 모델이 넘긴 티켓 번호, 주문 번호의 주인이 로그인한 계정인가. 없는 번호는 도구가 이유를 돌려준다
    if "ticket_id" in args:
        ticket = find_ticket(args["ticket_id"], context.db_path)
        if ticket is not None and ticket["fan_id"] != context.fan_id:
            return {"rule_id": OWNER_RULE, "reason": "로그인한 팬 본인의 티켓만 처리할 수 있어요."}
    if "order_id" in args:
        order = find_order(args["order_id"], context.db_path)
        if order is not None and order["fan_id"] != context.fan_id:
            return {"rule_id": OWNER_RULE, "reason": "로그인한 팬 본인의 주문만 처리할 수 있어요."}

    # 3. 공연장 확인: DB 공연 목록에 있는 공연 id 만 통과시킨다(주소를 넘기면 여기서 막혀 Nominatim 에 가지 않는다)
    if name == "get_event_venue":
        if "event_id" not in args or fan_db.get_event(args["event_id"], context.db_path) is None:
            return {"rule_id": VENUE_RULE, "reason": "공연 목록에 있는 공연의 공연장 위치만 찾을 수 있어요."}

    # TODO(함께 따라하기): 4. 팬레터 확인 단계를 여기에 더한다(name 이 "send_fan_letter" 일 때)
    #   - args 의 message 가 빈 글(공백만)이거나 FAN_LETTER_MAX_CHARS 보다 길면 LETTER_LENGTH_RULE(LTR-01) 과 이유를 돌려준다
    #   - message 에 링크, 전화번호, 이메일이 있으면(validators 의 LINK_PATTERN, PHONE_PATTERN, EMAIL_PATTERN) LETTER_CONTENT_RULE(LTR-02) 과 이유를 돌려준다
    #   - 위 import 줄에 FAN_LETTER_MAX_CHARS(config), LINK_PATTERN, EMAIL_PATTERN(validators) 을 더한다. 욕설, 비하는 입력 레일이 이미 판정했다

    return {"rule_id": "", "reason": ""}


# [보조 함수] 오늘 남은 팬아트 수
def remaining_fanarts(context) -> int:
    """로그인한 팬이 기준일에 더 만들 수 있는 팬아트 수를 돌려준다(등급별 하루 한도 - 오늘 만든 수). 0 이하면 더 만들 수 없다."""
    fan = fan_db.get_fan(context.fan_id, context.db_path)
    daily_limit = VISUAL["generation"]["daily_limit"][fan["membership"]]
    return daily_limit - count_today_fanarts(context.fan_id, context.db_path)


# [보조 함수] 이번 턴의 팬 메시지
def last_fan_message(messages: list) -> str:
    """대화 기록에서 마지막 팬(사람) 메시지 글을 돌려준다. 팬 메시지가 없으면 빈 문자열이다."""
    # 팬 메시지가 나올 때마다 덮어써 마지막 것이 남는다
    text = ""
    for message in messages:
        if message.type == "human":
            text = message.text
    return text


# [보조 함수] 이번 턴의 첫 팬아트 호출
def first_fanart_call_id(messages: list) -> str:
    """마지막 팬 메시지 뒤 AI 메시지들의 도구 호출 가운데 처음 나온 create_fanart 호출 id 를 돌려준다. 없으면 빈 문자열이다."""
    first_id = ""
    for message in messages:
        # 새 팬 메시지가 나오면 다시 센다. 승인으로 멈췄다 이어 간 실행도 같은 팬 메시지 뒤라 함께 센다
        if message.type == "human":
            first_id = ""
        # 도구 호출은 AI 메시지에만 있다
        if message.type != "ai":
            continue
        for call in message.tool_calls:
            # 아직 못 찾았을 때 처음 나온 팬아트 호출만 적는다
            if call["name"] == "create_fanart" and first_id == "":
                first_id = call["id"]
    return first_id


# [미들웨어] 역할별 도구 노출
@wrap_model_call
async def expose_tools_by_role(request, handler):
    """역할에 허용된 도구만 담아 부른 모델 응답을 돌려준다. 모델 호출마다 돈다."""
    # 역할은 로그인 정보(runtime.context)에서 읽는다. 팬이 대화에 "나는 운영자야" 라고 써도 바뀌지 않는다
    allowed_names = ROLE_TOOLS[request.runtime.context.role]
    allowed_tools = []
    for each_tool in request.tools:
        # ROLE_TOOLS 표에 있는 도구만 남긴다
        if each_tool.name in allowed_names:
            allowed_tools.append(each_tool)

    # override 는 이번 모델 호출에 넘길 도구 목록만 바꾼다. 실행할 수 있는 도구 목록은 그대로라 실행 전 검사가 한 번 더 본다
    return await handler(request.override(tools=allowed_tools))


# [미들웨어] 도구 실행 전 권한 확인
@wrap_tool_call
async def check_tool_permission(request, handler):
    """허락되지 않은 호출이면 도구 대신 오류 도구 결과를, 허락되면 안쪽 미들웨어(9절)와 도구를 실행한 결과를 돌려준다."""
    # 역할, 티켓과 주문의 주인, DB 공연 id 를 한 함수(permission_problem)로 확인한다
    problem = permission_problem(request.tool_call, request.runtime.context)

    # 막힘: handler 를 부르지 않으므로 안쪽 검사(팬아트 판정 등)와 도구가 모두 돌지 않는다
    if problem["reason"] != "":
        return blocked_tool_message(request.tool_call, "check_tool_permission", problem["rule_id"], problem["reason"])

    # 통과: handler 가 다음 미들웨어(목록에서 다음 순서)나 도구를 실행한다
    return await handler(request)


# [보조 함수] 업무 규칙 문제 찾기
def business_rule_problem(tool_call: dict, db_path) -> str:
    """취소, 환불 호출이 업무 규칙으로 거절될 이유(없는 번호, 이미 취소, 마감 지남 등)를 돌려준다. 실행할 수 있거나 규칙이 없는 도구면 빈 문자열이다."""
    args = tool_call["args"]

    # 티켓 취소: 도구(cancel_ticket)와 같은 견적 함수로 본다
    if tool_call["name"] == "cancel_ticket":
        # 번호가 없거나 없는 번호면 그 이유
        if "ticket_id" not in args:
            return "티켓 번호가 없어요."
        ticket = find_ticket(args["ticket_id"], db_path)
        if ticket is None:
            return "없는 티켓 번호예요."
        # 이미 취소, 마감 지남이면 견적 오류 문장, 취소할 수 있으면 빈 문자열
        return cancel_quote(ticket, db_path)["error"]

    # 굿즈 환불: 도구(request_goods_refund)와 같은 견적 함수로 본다
    if tool_call["name"] == "request_goods_refund":
        if "order_id" not in args:
            return "주문 번호가 없어요."
        order = find_order(args["order_id"], db_path)
        if order is None:
            return "없는 주문 번호예요."
        # 출고 전, 이미 요청, 주문 제작, 7일 지남이면 견적 오류 문장, 환불할 수 있으면 빈 문자열
        return refund_quote(order)["error"]

    # 여기서 확인할 규칙이 없는 도구(APPROVAL_TOOLS 에 새로 넣은 도구)는 승인을 묻는다
    return ""


# [보조 함수] 승인을 물을지
def should_ask_approval(request) -> bool:
    """권한 확인과 업무 규칙을 모두 통과할 호출이면 True(사람에게 묻는다), 아니면 False(묻지 않고 그대로 진행)를 돌려준다.

    False 인 호출은 멈추지 않고 실행 단계로 가서, 권한 문제는 check_tool_permission 이 막고 업무 규칙 문제는 도구가 이유를 돌려준다.
    """
    context = request.runtime.context

    # 1. 권한: 승인은 모델이 도구를 고른 직후, 실행 전 권한 확인보다 먼저 돈다. 막힐 호출까지 물으면 승인 카드가 남의 티켓을 노출한다
    if permission_problem(request.tool_call, context)["reason"] != "":
        # 막힐 호출: 묻지 않는다
        return False

    # 2. 업무 규칙: 없는 번호, 이미 취소된 티켓처럼 도구가 거절할 호출은 묻지 않고 도구가 이유를 돌려준다(rejected)
    #    이유가 없으면(빈 문자열) 실제로 실행될 호출이라 묻는다
    return business_rule_problem(request.tool_call, context.db_path) == ""


# [보조 함수] 승인 요청 설명
def describe_approval(tool_call, state, runtime) -> str:
    """승인 카드에 보여 줄 작업 설명(대상, 금액)을 돌려준다. 승인을 묻는 호출은 대상이 있고 견적 오류가 없다(should_ask_approval)."""
    db_path = runtime.context.db_path
    args = tool_call["args"]

    # 티켓 취소: 좌석, 수수료, 돌려받을 금액
    if tool_call["name"] == "cancel_ticket":
        ticket = find_ticket(args["ticket_id"], db_path)
        quote = cancel_quote(ticket, db_path)
        return (f"티켓 {ticket['ticket_id']} 예매 취소: {ticket['seat']}({ticket['grade']}), "
                f"수수료 {quote['fee']:,}원, 돌려받을 금액 {quote['refund']:,}원")

    # 굿즈 환불: 상품, 환불 예정 금액
    if tool_call["name"] == "request_goods_refund":
        order = find_order(args["order_id"], db_path)
        quote = refund_quote(order)
        return f"주문 {order['order_id']} {order['product_name']} 환불 요청: 환불 예정 {quote['amount']:,}원(반품 배송비 제외)"

    # 설명을 따로 만들지 않은 승인 도구는 도구 이름과 인자를 그대로 보여 준다
    return f"{tool_call['name']} 실행: {args}"


# 사람 승인: 위험도가 높은 도구는 승인(approve) 또는 거절(reject)을 받을 때까지 멈춘다
# description: 승인 카드에 보일 설명을 만드는 함수, when: 이 호출을 물을지 정하는 함수(False 면 멈추지 않는다)
# 멈춘 자리는 바깥 그래프의 체크포인터에 저장된다(이 에이전트는 바깥 그래프의 노드라 체크포인터를 따로 두지 않는다)
APPROVAL_CONFIG = {}
for approval_tool in APPROVAL_TOOLS:
    APPROVAL_CONFIG[approval_tool] = {
        "allowed_decisions": ["approve", "reject"],
        "description": describe_approval,
        "when": should_ask_approval,
    }
approval_mw = HumanInTheLoopMiddleware(interrupt_on=APPROVAL_CONFIG)


# [미들웨어] 팬아트 생성 전 검사
@wrap_tool_call
async def fanart_quota_and_policy(request, handler):
    """막은 팬아트 호출이면 오류 도구 결과를, 통과했거나 팬아트가 아닌 호출이면 안쪽을 실행한 결과를 돌려준다.

    검사 순서: 한 메시지 한 장 -> 하루 한도 -> 그림 요청 정책(Jev). 비용이 없는 검사를 앞에 두고, 막으면 그림 API 를 부르지 않는다.
    """
    call = request.tool_call
    # 팬아트가 아닌 도구: 검사 없이 안쪽으로 넘긴다
    if call["name"] != "create_fanart":
        return await handler(request)
    context = request.runtime.context

    # 1. 한 메시지 한 장: 이번 턴의 첫 팬아트 호출만 통과한다
    # 같은 AI 메시지의 두 번째 호출, 결과를 본 뒤 다시 부른 호출, 승인으로 멈췄다 이어 간 뒤의 호출을 모두 막는다
    if first_fanart_call_id(request.state["messages"]) != call["id"]:
        return blocked_tool_message(call, "fanart_quota_and_policy", FANART_RUN_RULE, "팬아트는 팬 메시지 한 번에 한 장만 만들 수 있어요.")

    # 2. 하루 한도: 비용이 들지 않는 DB 조회라 Jev 보다 먼저 본다
    if remaining_fanarts(context) <= 0:
        return blocked_tool_message(call, "fanart_quota_and_policy", QUOTA_RULE, VISUAL["blocked_replies"]["over_limit"])

    # 3. 그림 요청 정책(Jev): 모델이 고쳐 쓴 요청만 보지 않고 팬이 직접 쓴 메시지도 함께 판정한다
    tool_request = ""
    # 모델이 request 인자를 빠뜨렸으면 팬 메시지만으로 판정한다
    if "request" in call["args"]:
        tool_request = call["args"]["request"]
    text = f"팬 메시지: {last_fan_message(request.state['messages'])}\n도구 요청: {tool_request}"
    # 판정이 오류로 끝나면 판정하지 못한 요청이므로 그림 API 를 부르지 않는다(fail-closed)
    # Jev 클라이언트는 스스로 다시 시도하지 않는다. 여기서도 다시 부르지 않고, 팬이 잠시 뒤 다시 보내게 안내한다
    try:
        judgement = await jev_policy_judgement({"fanart_request": text}, IMAGE_REQUEST_POLICY, IMAGE_RULES)
    except Exception:
        # 판정 실패: RAIL-ERROR 로 막고 REF-10 안내(잠시 문제가 생겨 처리하지 못했다)를 이유로 준다
        return blocked_tool_message(call, "fanart_quota_and_policy", RAIL_ERROR_RULE, reply_for_rule(RAIL_ERROR_RULE))
    # 금지 주제(IMG-01~07)를 고른 경우에만 막는다. 확률이 높아도 주제를 못 고르면 통과시킨다
    # 모델이 덧붙인 말에 확률만 높게 나온 오차단을 줄이고, 뒤의 장면 칸, 고정 안전 틀, 생성 후 검사가 받친다
    rule_id = judgement["rule_id"]
    if judgement["probability"] > IMAGE_POLICY_THRESHOLD and rule_id != "":
        # 막힌 요청도 기록한다(같은 주제가 3번 막히면 7일 정지하는 규칙의 근거). 하루 횟수에는 넣지 않는다
        record_fanart_request(context.fan_id, f"그림 요청 정책 위반({rule_id})", "차단", rule_id, context.db_path)
        return blocked_tool_message(call, "fanart_quota_and_policy", rule_id, VISUAL["blocked_replies"]["input_blocked"])

    # 세 검사를 모두 통과: 안쪽 미들웨어(그림 검사)와 그림 도구를 실행한다
    return await handler(request)


# [미들웨어] 팬아트 생성 후 검사
@wrap_tool_call
async def check_fanart_image(request, handler):
    """팬아트 그림을 모더레이션, 브랜드 검사 순서로 검사한 도구 결과를 돌려준다. 통과하면 워터마크를 찍은 그림과 남은 횟수를,
    걸리거나 판정이 실패하면 그림을 막은 그림 폴더(blocked)로 옮긴 오류 결과를 담는다.

    artifact 칸: generated(그림 API 를 불렀는가), path(보여 줄 파일, 막혔으면 None), verdicts(검사별 판정),
    remaining(오늘 남은 횟수), rule_id(막은 규칙, 통과면 빈 문자열), blocked_path(막은 그림을 옮긴 파일, 막혔을 때만)
    """
    # 먼저 안쪽(그림 도구)을 실행하고, 돌아온 결과를 검사한다
    result = await handler(request)
    # 팬아트가 아니거나 이미 막힌(오류) 결과: 검사할 그림이 없어 그대로 돌려준다
    if request.tool_call["name"] != "create_fanart" or result.status == "error":
        return result
    # 장면을 알 수 없어 그리지 않았으면 검사할 그림이 없다(도구가 다시 묻는 문장을 그대로 돌려준다)
    if not result.artifact["generated"]:
        return result
    context = request.runtime.context
    path = result.artifact["path"]

    # 1. 모더레이션. 통과했을 때만 브랜드 검사를 한다(실패한 그림에 비전 모델 비용을 쓰지 않는다)
    verdicts = {"모더레이션": "passed", "브랜드 검사": "info"}
    content = VISUAL["blocked_replies"]["output_blocked"]
    # 판정이 오류로 끝나면 검사하지 못한 그림이므로 보여 주지 않는다(fail-closed)
    # OpenAI 클라이언트가 이미 몇 번 다시 시도한 뒤의 오류라 여기서 다시 부르지 않는다
    try:
        moderation = await moderate_image(path)
        rule_id = moderation["rule_id"]
        # 모더레이션 통과: 브랜드 검사를 하고, 그 결과의 규칙 id(통과면 빈 문자열)로 바꾼다
        if moderation["passed"]:
            brand = await brand_check(path)
            rule_id = brand["rule_id"]
            verdicts["브랜드 검사"] = "passed"
            if not brand["passed"]:
                verdicts["브랜드 검사"] = "blocked"
        # 모더레이션 실패: 브랜드 검사는 하지 않고 모더레이션 규칙 id(MOD-범주)를 남긴다
        else:
            verdicts["모더레이션"] = "blocked"
    except Exception:
        # 판정 실패: RAIL-ERROR 로 막고, 두 검사 모두 판정 없음(info)으로 두고 REF-10 안내를 보낸다
        rule_id = RAIL_ERROR_RULE
        verdicts = {"모더레이션": "info", "브랜드 검사": "info"}
        content = reply_for_rule(RAIL_ERROR_RULE)

    # 2. 실패: 팬에게 보여 주지 않고 차단으로 기록한다. 막힌 그림은 하루 횟수에 넣지 않는다
    #    그림은 지우지 않고 저장 폴더 안의 blocked 폴더로 옮긴다. 지우면 오차단인지(검사가 틀렸는지) 나중에 확인할 수 없다
    if rule_id != "":
        blocked_path = Path(path).parent / "blocked" / Path(path).name
        blocked_path.parent.mkdir(parents=True, exist_ok=True)
        Path(path).replace(blocked_path)
        record_fanart_request(context.fan_id, result.artifact["summary"], "차단", rule_id, context.db_path)
        artifact = {"generated": True, "path": None, "verdicts": verdicts, "remaining": remaining_fanarts(context),
                    "rule_id": rule_id, "blocked_path": str(blocked_path)}
        return ToolMessage(
            content=content, artifact=artifact, tool_call_id=result.tool_call_id,
            name=result.name, status="error", response_metadata={"rail": "check_fanart_image", "rule_id": rule_id},
        )

    # 3. 통과: 'AI 생성 팬아트' 를 찍고 생성완료로 기록한다
    stamp_watermark(path)
    record_fanart_request(context.fan_id, result.artifact["summary"], "생성완료", None, context.db_path)
    remaining = remaining_fanarts(context)
    artifact = {"generated": True, "path": path, "verdicts": verdicts, "remaining": remaining, "rule_id": ""}
    # 그린 장면 요약을 결과 글에 넣는다. 모델이 그림을 소개한 말이 출력 레일 사실 대조의 근거에 있어야 막히지 않는다
    return ToolMessage(
        content=f"팬아트를 만들었어요. 그린 장면은 '{result.artifact['summary']}' 예요. 오늘 남은 횟수는 {remaining}회예요.", artifact=artifact,
        tool_call_id=result.tool_call_id, name=result.name,
    )


# [보조 함수] 숨은 지시가 든 절 빼기
def filter_documents(docs: list) -> dict:
    """검색 문서(Document) 목록에서 숨은 지시가 든 절을 빼고 {"kept": 남긴 문서, "dropped_ids": 뺀 절 id} 를 돌려준다."""
    kept = []
    dropped_ids = []
    for doc in docs:
        # 숨은 지시 모양이 있는 절: 빼고 id 만 적는다
        if has_hidden_instruction(doc.page_content):
            dropped_ids.append(doc.metadata["source_id"])
        # 깨끗한 절: 남긴다
        else:
            kept.append(doc)
    return {"kept": kept, "dropped_ids": dropped_ids}


# [미들웨어] 도구 실행 후 결과 검사
@wrap_tool_call
async def check_tool_result(request, handler):
    """규정 검색 결과면 숨은 지시가 든 절을 뺀 도구 결과를, 뺄 절이 없거나 다른 도구면 받은 결과를 그대로 돌려준다."""
    # 먼저 안쪽(도구)을 실행하고, 모델이 읽기 전에 결과를 검사한다
    result = await handler(request)
    # 규정 검색이 아니거나 막힌 결과: 검사할 문서가 없다
    if request.tool_call["name"] != "search_policy" or result.status == "error":
        return result

    # 교안 01 검색 레일과 같은 정규식 검사를 절마다 한다
    # 이 에이전트는 검색이 도구라서 NeMo 검색 레일 대신 도구 결과를 받는 이 미들웨어가 검사한다
    filtered = filter_documents(result.artifact)
    # 뺀 절이 없음: 원래 결과를 그대로 쓴다(rail 표시도 남기지 않는다)
    if len(filtered["dropped_ids"]) == 0:
        return result

    # 뺀 절 id 는 response_metadata 에만 남긴다. 모델에게는 남은 절만 간다
    return ToolMessage(
        content=format_documents(filtered["kept"]), artifact=filtered["kept"], tool_call_id=result.tool_call_id,
        name=result.name, response_metadata={"rail": "check_tool_result", "rule_id": "", "dropped_ids": filtered["dropped_ids"]},
    )


# [미들웨어] 회원 정보 가리기
@wrap_tool_call
async def mask_member_info(request, handler):
    """회원 정보 도구 결과의 전화번호, 이메일을 가린 도구 결과를 돌려준다. 다른 도구 결과는 그대로 돌려준다."""
    # 먼저 안쪽(도구)을 실행하고, 모델이 읽기 전에 결과를 가린다
    result = await handler(request)
    # 회원 정보 도구가 아님: 가릴 연락처가 없다
    if request.tool_call["name"] not in MEMBER_INFO_TOOLS:
        return result

    # content 만 바꾸고 status, artifact, 실행 레일 표시는 그대로 둔다
    # 규정 검색 결과는 가리지 않는다. 공식 안내 이메일(개인정보보호팀 주소)까지 가리면 정상 안내가 망가진다
    return result.model_copy(update={"content": mask_pii(result.text)})


# 최종 답변의 전화번호, 이메일을 가린다. 팬이 쓴 입력과 도구 결과는 가리지 않는다(도구 결과는 mask_member_info 가 맡는다)
# 전화번호 정규식은 Guardrails AI 검증기(validators.py)와 같은 것을 쓴다
pii_mws = [
    PIIMiddleware("kr_phone", detector=PHONE_PATTERN.pattern, strategy="mask",
                  apply_to_input=False, apply_to_tool_results=False, apply_to_output=True),
    PIIMiddleware("email", strategy="mask", apply_to_input=False, apply_to_tool_results=False, apply_to_output=True),
]


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.guards.execution
    # 모델과 Jev 를 부르지 않는 권한 확인만 실행한다
    from types import SimpleNamespace

    from app.core.schemas import AgentContext

    fan_f0002 = AgentContext(fan_id="F0002", role="fan")
    fan_f0003 = AgentContext(fan_id="F0003", role="fan")
    print("F0002 가 T00003 취소:", permission_problem({"name": "cancel_ticket", "args": {"ticket_id": "T00003"}}, fan_f0002))
    print("F0003 가 T00003 취소:", permission_problem({"name": "cancel_ticket", "args": {"ticket_id": "T00003"}}, fan_f0003))
    print("팬이 lookup_fan:", permission_problem({"name": "lookup_fan", "args": {"fan_id": "F0004"}}, fan_f0002))
    print("없는 공연 위치:", permission_problem({"name": "get_event_venue", "args": {"event_id": "서울특별시 누리구"}}, fan_f0002))
    # 승인 설명 함수는 runtime.context 만 읽으므로 context 칸 하나만 가진 객체를 넘긴다
    node_runtime = SimpleNamespace(context=fan_f0003)
    print("F0003 승인 설명:", describe_approval({"name": "cancel_ticket", "args": {"ticket_id": "T00097"}}, {}, node_runtime))
    print("이미 취소된 T00015 의 업무 규칙 문제:", business_rule_problem({"name": "cancel_ticket", "args": {"ticket_id": "T00015"}}, fan_f0003.db_path))
    print("F0005 오늘 남은 팬아트:", remaining_fanarts(AgentContext(fan_id="F0005", role="fan")))
    print("승인 도구:", list(APPROVAL_CONFIG), "/ 그림 정책 금지 주제:", list(IMAGE_RULES))
    print("결과를 가리는 회원 정보 도구:", MEMBER_INFO_TOOLS, "/ 가린 예:", mask_pii("010-1234-5678, lumi@example.com"))
