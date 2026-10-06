"""그래프 층: 노드와 엣지를 이어 그래프를 컴파일한다."""
from langgraph.graph import END, START, StateGraph

from app.graph.edges import dispatch
from app.graph.nodes import (
    planner,
    publisher,
    researcher,
    reviewer,
    supervisor,
    synthesizer,
    writer,
)
from app.graph.state import Context, State


# [그래프 조립] 노드를 등록하고 엣지를 이어 컴파일한다.
def build_graph():
    """계획 -> 병렬 조사 -> 종합 -> 감독 -> 작성 -> 검수 -> 발행 그래프를 컴파일해 돌려준다."""
    # State 모양과 실행 컨텍스트 모양을 알려 주고 빌더를 만든다.
    builder = StateGraph(State, context_schema=Context)
    # Send 대상(researcher)과 핸드오프 대상(reviewer)은 다른 노드로 둔다. 병렬 조사와 제어권 이동이 섞이지 않는다.
    # TODO: 노드를 등록하고 고정 엣지와 Send 분배 엣지를 이어 컴파일하기
    # 1) planner, researcher, synthesizer, supervisor, writer, reviewer, publisher 를 add_node 로 등록한다
    # 2) 핸드오프로 움직이는 writer 는 destinations 로 갈 수 있는 곳(reviewer, supervisor)을 알려 준다. supervisor 와 reviewer 는 반환 타입의 Literal 이 갈 곳을 알려 준다
    # 3) START -> planner, planner -> dispatch(갈 곳 ["researcher", "synthesizer"]), researcher -> synthesizer -> supervisor, publisher -> END 를 잇는다
    # 4) builder.compile() 을 돌려준다
    raise NotImplementedError("TODO를 완성하세요")
