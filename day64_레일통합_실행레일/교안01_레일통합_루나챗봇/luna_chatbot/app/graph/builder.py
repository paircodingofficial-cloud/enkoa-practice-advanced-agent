"""그래프 층: 노드를 등록하고 엣지로 이어 레일 챗봇 그래프를 컴파일한다."""
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from app.core.schemas import ChatContext
from app.graph.edges import route_after_input, route_after_lookup, route_after_output, route_after_router
from app.graph.nodes import (
    chitchat,
    generate,
    input_rail,
    my_orders,
    my_tickets,
    output_rail,
    refuse,
    retrieval_rail,
    retrieve,
    rewrite_query,
    router,
    venue_lookup,
)
from app.graph.state import GuardedChatState


# [그래프 조립] 레일 챗봇
def build_app(checkpointer=None, interrupt_before=None):
    """노드 12개를 이어 컴파일한 레일 챗봇 그래프를 돌려준다. checkpointer 를 주면 대화 ID 마다 State 를 저장한다.

    interrupt_before 에 노드 이름 목록을 주면 그 노드 앞에서 멈춘다(평가의 --routes-only 가 답변 모델 앞에서 멈출 때 쓴다).
    """
    # 1. 빌더: 노드가 읽고 고칠 State 와 실행할 때 넘길 ChatContext 의 모양을 정한다
    builder = StateGraph(GuardedChatState, context_schema=ChatContext)

    # 2. 노드 등록: 레일 노드 세 개, 거절 노드 한 개, 라우터 노드 한 개, 일상 대화 노드 한 개, 조회 노드 세 개, RAG 노드 세 개
    builder.add_node("input_rail", input_rail)
    builder.add_node("refuse", refuse)
    builder.add_node("router", router)
    builder.add_node("chitchat", chitchat)
    builder.add_node("venue_lookup", venue_lookup)
    builder.add_node("my_tickets", my_tickets)
    builder.add_node("my_orders", my_orders)
    builder.add_node("rewrite_query", rewrite_query)
    builder.add_node("retrieve", retrieve)
    builder.add_node("retrieval_rail", retrieval_rail)
    builder.add_node("generate", generate)
    builder.add_node("output_rail", output_rail)

    # 3. 엣지: 입력 레일 뒤, 라우터 뒤, 내 정보 조회 뒤, 출력 레일 뒤에서 갈라진다
    builder.add_edge(START, "input_rail")
    builder.add_conditional_edges("input_rail", route_after_input, {"refuse": "refuse", "router": "router"})
    builder.add_conditional_edges("router", route_after_router, {
        "end": END,
        "chitchat": "chitchat",
        "venue_lookup": "venue_lookup",
        "my_tickets": "my_tickets",
        "my_orders": "my_orders",
        "rewrite_query": "rewrite_query",
    })

    # 일상 대화는 검색하지 않고 답한 뒤 출력 레일로 간다
    builder.add_edge("chitchat", "output_rail")

    # DB 질문은 조회한 정보만으로 답한다(검색어 다시 쓰기, 검색, 검색 레일을 건너뛴다)
    # 내 티켓, 내 주문은 섞인 질문이면 검색 경로로, 로그인하지 않았으면 안내를 남기고 끝난다
    builder.add_edge("venue_lookup", "generate")
    lookup_targets = {"generate": "generate", "rewrite_query": "rewrite_query", "end": END}
    builder.add_conditional_edges("my_tickets", route_after_lookup, lookup_targets)
    builder.add_conditional_edges("my_orders", route_after_lookup, lookup_targets)

    # RAG 경로는 한 줄로 이어지고, 모델이 만든 답은 모두 출력 레일을 지나야 끝난다
    builder.add_edge("rewrite_query", "retrieve")
    builder.add_edge("retrieve", "retrieval_rail")
    builder.add_edge("retrieval_rail", "generate")
    builder.add_edge("generate", "output_rail")

    # 출력 레일 뒤: 근거에 없는 내용(OUT-05), 규정에 없는 예외 약속(OUT-09)으로 처음 막혔으면 답변 노드로 한 번 돌아가 다시 쓴다
    # 검색, 조회 노드로는 돌아가지 않으므로 이번 턴의 근거를 그대로 쓴다. 그 밖에는 끝난다(막혔으면 거절 문장이 이미 들어 있다)
    builder.add_conditional_edges("output_rail", route_after_output, {"end": END, "chitchat": "chitchat", "generate": "generate"})
    builder.add_edge("refuse", END)

    # 4. 컴파일
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


# [보조 함수] 그래프 그림 저장
def draw_graph_png(app, path) -> Path:
    """컴파일한 그래프를 PNG 로 그려 path 에 저장하고 그 경로를 돌려준다(mermaid.ink 무료 서버를 쓴다)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(app.get_graph().draw_mermaid_png())
    return path


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.builder
    # 체크포인터 없이 컴파일해 노드와 엣지만 본다(API 를 부르지 않는다). 그림 파일은 draw_graph_png(app, "images/graph.png")
    graph = build_app().get_graph()
    print("노드:", list(graph.nodes))
    print("엣지:")
    for edge in graph.edges:
        label = ""
        if edge.conditional:
            label = " (조건)"
        print(" ", edge.source, "->", edge.target + label)
    print("\nmermaid 도식:")
    print(graph.draw_mermaid())
