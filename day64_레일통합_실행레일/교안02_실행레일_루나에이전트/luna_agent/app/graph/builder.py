"""그래프 층: 루나 에이전트(create_agent 와 실행 레일 미들웨어)를 노드 하나로 넣고, 그 앞뒤에 레일 노드를 이어 바깥 그래프를 컴파일한다.

바깥 그래프: START -> input_rail -> agent -> output_rail -> END
- input_rail 이 막으면 refuse -> END (모델과 도구는 돌지 않는다)
- output_rail 이 다시 쓰면 고쳐질 규칙(OUT-05, OUT-09)으로 막았고 아직 다시 쓰지 않았으면 regenerate -> output_rail
입력, 출력 레일은 요청마다 한 번 돌아 노드로 둔다. 실행 레일은 에이전트의 도구 반복 안에서 돌아 미들웨어로 둔다.

미들웨어 순서 규칙(langchain 1.3 create_agent)
- before_model 훅은 목록 순서대로, after_model 훅은 목록의 역순으로 돈다.
- wrap_model_call, wrap_tool_call 은 목록의 첫 미들웨어가 가장 바깥이다. 바깥이 막으면 안쪽은 돌지 않는다.
그래서 도구 실행 전 검사(2~6번 wrap_tool_call)는 권한 확인이 가장 먼저 돌고, 모델 호출 뒤 훅인 승인(7번)과 답변 가림(8, 9번)은
목록의 역순으로 돌아 답변을 가린 다음 승인을 묻는다.
"""
import sys
from pathlib import Path

from langchain.agents import create_agent
from langgraph.graph import END, START, StateGraph

from app.core.config import llm
from app.core.schemas import AgentContext
from app.graph.edges import route_after_input, route_after_output
from app.graph.nodes import agent_system_prompt, input_rail, output_rail, refuse, regenerate
from app.graph.state import LunaState
from app.guards.execution import (
    approval_mw,
    check_fanart_image,
    check_tool_permission,
    check_tool_result,
    expose_tools_by_role,
    fanart_quota_and_policy,
    mask_member_info,
    pii_mws,
)
from app.tools.booking_tools import BOOKING_TOOLS
from app.tools.fanart import create_fanart

# 에이전트에 붙이는 도구 열 개. 역할에 따라 모델에게 보이는 도구는 expose_tools_by_role 이 줄인다
# TODO(함께 따라하기): app.tools.fan_letter 의 send_fan_letter 를 import 해 ALL_TOOLS 끝에 붙인다(사람 승인이 필요 없어 APPROVAL_TOOLS 에는 넣지 않는다)
ALL_TOOLS = BOOKING_TOOLS + [create_fanart]

# [미들웨어] 실행 레일의 순서와 이유. 번호는 이 목록의 순서다(교안 그림 middleware_order.png 의 번호와 같다)
# 도구 쪽(2~6, wrap_tool_call): 앞이 바깥이다. 바깥이 막으면 안쪽 검사와 도구는 돌지 않으므로 싼 검사, 넓은 검사를 앞에 둔다
# 모델 뒤 훅(7~9, after_model): 목록의 역순(9, 8, 7)으로 돈다. 답변 가림이 먼저 끝나고, 승인은 마지막에 도구 호출만 본다
MIDDLEWARE = [
    expose_tools_by_role,     # 1. 모델 호출마다: 역할 밖 도구는 모델이 아예 보지 못하게 한다
    check_tool_permission,    # 2. 도구 실행 전 가장 바깥: 남의 데이터, 역할 밖 도구, 없는 공연 id 는 다른 검사보다 먼저 막는다
    fanart_quota_and_policy,  # 3. 권한을 통과한 팬아트 호출만: 한 메시지 한 장, 하루 한도, 그림 정책을 보고 막으면 유료 그림 API 를 부르지 않는다
    check_fanart_image,       # 4. 그림 API 바로 바깥: 만든 그림을 검사하고 워터마크를 찍는다
    check_tool_result,        # 5. 도구 바로 바깥: 규정 검색 결과의 숨은 지시를 모델이 읽기 전에 뺀다
    mask_member_info,         # 6. 도구 바로 바깥: 회원 정보 도구 결과의 전화번호, 이메일을 모델이 읽기 전에 가린다
    approval_mw,              # 7. 모델이 도구를 고른 직후: 취소, 환불은 사람 승인 전까지 멈춘다(권한과 업무 규칙을 통과할 호출만 묻는다)
] + pii_mws                   # 8, 9. 모델 호출 뒤: 답변의 전화번호, 이메일을 가린다


# [그래프 조립] 에이전트 노드
def build_agent():
    """실행 레일과 사람 승인을 붙인 루나 에이전트(컴파일한 create_agent 그래프)를 돌려준다. 바깥 그래프의 agent 노드가 된다."""
    # 체크포인터는 바깥 그래프 것을 같이 쓴다(5절)
    return create_agent(
        model=llm,
        tools=ALL_TOOLS,
        system_prompt=agent_system_prompt(),
        context_schema=AgentContext,
        middleware=MIDDLEWARE,
    )


# [그래프 조립] 루나 에이전트 앱
def build_app(checkpointer=None):
    """레일 노드 둘, 거절 노드, 다시 쓰기 노드, 에이전트 노드를 이어 컴파일한 바깥 그래프를 돌려준다. checkpointer 를 주면 대화 ID 마다 저장한다."""
    # 1. 빌더: 노드가 읽고 고칠 State 와 실행마다 넘길 로그인 정보(AgentContext)의 모양을 정한다
    builder = StateGraph(LunaState, context_schema=AgentContext)

    # 2. 노드 등록: 레일 노드 둘, 거절 노드, 다시 쓰기 노드, 에이전트 노드(컴파일한 create_agent 그래프를 그대로 넣는다)
    builder.add_node("input_rail", input_rail)
    builder.add_node("refuse", refuse)
    builder.add_node("agent", build_agent())
    builder.add_node("output_rail", output_rail)
    builder.add_node("regenerate", regenerate)

    # 3. 엣지: 입력 레일 뒤와 출력 레일 뒤에서 갈라진다
    builder.add_edge(START, "input_rail")
    builder.add_conditional_edges("input_rail", route_after_input, {"refuse": "refuse", "agent": "agent"})
    builder.add_edge("refuse", END)
    builder.add_edge("agent", "output_rail")
    builder.add_conditional_edges("output_rail", route_after_output, {"regenerate": "regenerate", "end": END})
    builder.add_edge("regenerate", "output_rail")

    # 4. 컴파일: checkpointer 는 대화 기록과 승인 대기 실행(에이전트 노드 안의 멈춘 자리)을 thread_id 별로 저장한다
    return builder.compile(checkpointer=checkpointer)


# [보조 함수] 그래프 그림 저장
def draw_graph_png(app, path) -> Path:
    """컴파일한 그래프를 PNG 로 그려 path 에 저장하고 그 경로를 돌려준다(mermaid.ink 무료 서버를 쓴다)."""
    graph = app.get_graph()

    # 1. 이름 고치기: 노드 이름에 대괄호가 있으면(예: 미들웨어 노드 PIIMiddleware[email]) mermaid.ink 가 400 을 낸다
    # 소괄호도 mermaid 의 모양 문법이라 400 이 난다(실측). 그래서 대괄호를 공백으로 바꿔 그린다: PIIMiddleware email
    for node_id, node in list(graph.nodes.items()):
        clean_name = node.name.replace("[", " ").replace("]", "")
        graph.nodes[node_id] = node.copy(name=clean_name)

    # 2. 저장: 그림 서비스가 돌려준 PNG 바이트를 파일로 쓴다
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(graph.draw_mermaid_png())
    return path


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.builder
    # 그래프를 만들기만 한다(모델을 부르지 않는다). --png 를 붙이면 mermaid.ink(무료)로 그림 두 장을 images/ 에 저장한다
    from app.core.config import PROJECT_DIR

    app = build_app()
    agent = build_agent()
    print("도구:", [each_tool.name for each_tool in ALL_TOOLS])
    print("바깥 그래프 노드:", list(app.get_graph().nodes))
    print("에이전트 노드 안의 노드:", list(agent.get_graph().nodes))
    if "--png" in sys.argv:
        print("바깥 그래프 그림 저장:", draw_graph_png(app, PROJECT_DIR / "images" / "luna_graph.png"))
        print("에이전트 노드 그림 저장:", draw_graph_png(agent, PROJECT_DIR / "images" / "agent_graph.png"))
