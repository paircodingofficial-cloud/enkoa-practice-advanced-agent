"""그래프 층: 갈림길에서 다음 노드를 정하는 라우팅 함수. State 를 읽기만 하고 고치지 않는다.

함수는 다음 노드의 이름(문자열)을 돌려준다. builder.py 가 그 이름을 실제 노드(또는 END)에 잇는다.
"""
from app.graph.state import GuardedChatState

# 라우터가 고른 경로 이름(core/prompts.py 의 ROUTES) -> 다음 노드 이름. "end" 는 그래프를 끝낸다(정해 둔 답을 이미 남겼다)
ROUTE_NODES = {
    "out_of_scope": "end",
    "chitchat": "chitchat",
    "venue": "venue_lookup",
    "my_ticket": "my_tickets",
    "my_order": "my_orders",
    "my_ticket_rule": "my_tickets",
    "my_order_rule": "my_orders",
    "rag": "rewrite_query",
}

# 내 티켓, 내 주문 조회 노드가 남긴 경로 이름 -> 다음 노드 이름
# DB 질문은 검색 없이 바로 답하고, 섞인 질문(규정도 묻는 질문)은 로그인하지 않았어도 검색 경로로 간다
# login 은 로그인하지 않은 팬의 DB 질문이다. 로그인 안내를 이미 남겼으므로 끝낸다
LOOKUP_NODES = {
    "my_ticket": "generate",
    "my_order": "generate",
    "my_ticket_rule": "rewrite_query",
    "my_order_rule": "rewrite_query",
    "login": "end",
}


# [라우팅 함수] 입력 레일 뒤
def route_after_input(state: GuardedChatState) -> str:
    """입력 레일이 막았으면 "refuse", 통과했으면 "router" 를 돌려준다."""
    # 막은 흐름 이름이 남아 있으면 막힌 것이다. 거절 노드로 간다
    if state["blocked_by"] != "":
        return "refuse"

    # 통과(가림 포함)했으면 라우터가 경로를 고른다
    return "router"


# [라우팅 함수] 라우터 뒤
def route_after_router(state: GuardedChatState) -> str:
    """라우터가 고른 경로(route)에 맞는 다음 노드 이름을 돌려준다."""
    # 라우터는 ROUTES 안의 이름만 남기므로 표에서 바로 찾는다
    return ROUTE_NODES[state["route"]]


# [라우팅 함수] 내 정보 조회 뒤
def route_after_lookup(state: GuardedChatState) -> str:
    """조회 노드가 남긴 경로(route)에 맞는 다음 노드 이름(generate, rewrite_query, end)을 돌려준다."""
    # 로그인하지 않은 DB 질문은 조회 노드가 route 를 login 으로 바꿔 두었다
    return LOOKUP_NODES[state["route"]]


# [라우팅 함수] 출력 레일 뒤
def route_after_output(state: GuardedChatState) -> str:
    """출력 레일이 고칠 점을 남겼으면 그 경로의 답변 노드("chitchat", "generate")를, 아니면 "end" 를 돌려준다."""
    # 고칠 점은 출력 레일이 RETRY_RULES 의 규칙으로 처음 막았을 때만 남는다. 답변 노드가 쓰고 나면 비우므로 두 번 돌아가지 않는다
    if state["retry_feedback"] == "":
        return "end"

    # 일상 대화의 답은 chitchat 이 다시 쓰고, 나머지 경로(DB 조회, 검색)의 답은 generate 가 이번 턴 근거로 다시 쓴다
    if state["route"] == "chitchat":
        return "chitchat"
    return "generate"


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.edges
    print("입력 레일이 막았을 때:", route_after_input({"blocked_by": "jev policy input"}))
    print("입력 레일을 지났을 때:", route_after_input({"blocked_by": ""}))
    for route_name in ROUTE_NODES:
        print(f"라우터 경로 {route_name} ->", route_after_router({"route": route_name}))
    for route_name in LOOKUP_NODES:
        print(f"조회 뒤 경로 {route_name} ->", route_after_lookup({"route": route_name}))
    print("출력 레일이 통과시켰을 때:", route_after_output({"retry_feedback": "", "route": "rag"}))
    print("출력 레일이 다시 만들라고 했을 때(검색 경로):", route_after_output({"retry_feedback": "[고칠 점] ...", "route": "rag"}))
    print("출력 레일이 다시 만들라고 했을 때(일상 대화):", route_after_output({"retry_feedback": "[고칠 점] ...", "route": "chitchat"}))
