"""그래프 층: 노드를 등록하고 시작과 병렬 분배 엣지를 잇는다. 나머지 이동은 노드의 Command 가 정한다."""
from langgraph.graph import END, START, StateGraph

from app.graph.edges import dispatch
from app.graph.nodes import (
    analysis_planner,
    data_analyst,
    report_writer,
    reviewer,
    supervisor,
    worker,
)
from app.graph.state import TeamState


# [그래프 조립] 슈퍼바이저, 분석 계획, 분석가, 워커, 작성자, 검수자를 등록하고 시작 엣지와 Send 분배 엣지를 잇는다
def build_graph():
    """슈퍼바이저 중심으로 노드를 연결해 컴파일한 그래프를 돌려준다."""
    # TODO: 노드를 등록하고 START 엣지, Send 분배 엣지, 분석가의 복귀 엣지를 이어 컴파일하기
    # 1) StateGraph 빌더를 TeamState 로 만든다
    # 2) 노드 일곱 개를 등록한다. doc_reader 와 web_researcher 는 같은 worker 함수를 쓴다.
    #    Command 로 움직이는 노드(supervisor, doc_reader, web_researcher, report_writer, reviewer)는 destinations 에 갈 수 있는 노드를 적는다
    #    (그래프 그림에 화살표를 그리는 용도, 실행에는 영향 없음). README 의 팀 구성 그림과 규칙 그림을 보고 정한다
    # 3) START -> supervisor, analysis_planner -> dispatch(갈 곳 data_analyst, supervisor), data_analyst -> supervisor 를 잇고 compile() 한 그래프를 돌려준다
    raise NotImplementedError("TODO를 완성하세요")
