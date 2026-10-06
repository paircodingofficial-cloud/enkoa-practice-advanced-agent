"""도구 층: 작성자 에이전트가 제어권을 넘기는 핸드오프 도구(검수 요청, 추가 조사 요청)."""
from langchain.tools import tool
from langgraph.types import Command


# [핸드오프 도구] 검수 요청: 다 쓴 보고서의 파일 이름을 reviewer 에게 넘깁니다.
@tool
def request_review(report_path: str) -> Command:
    """보고서를 저장한 뒤 파일 이름을 검수자(reviewer)에게 넘깁니다."""
    # graph=Command.PARENT 가 에이전트 안이 아니라 바깥 그래프의 reviewer 로 이동하게 합니다.
    # update 는 바깥 State 에 반영되므로 reviewer 가 읽는 report_path 필드만 채웁니다.
    return Command(goto="reviewer", graph=Command.PARENT, update={"report_path": report_path})


# [핸드오프 도구] 추가 조사 요청: 빠진 자료를 적어 supervisor 에게 넘깁니다.
@tool
def request_research(missing: str) -> Command:
    """팀 기록만으로 보고서를 쓸 수 없을 때 무엇이 빠졌는지 알리고 추가 조사를 요청합니다."""
    # TODO: 부모 그래프의 supervisor 로 넘어가는 핸드오프 Command 만들기
    # 1) goto 는 supervisor, graph 는 Command.PARENT 로 정한다. 조사 담당에게 바로 가지 않고 supervisor 를 거쳐야 반려 횟수 상한(MAX_ROUNDS) 검사를 받는다
    # 2) update 에는 review 를 {"passed": False} 로, 빠진 자료(missing)를 feedback 으로 실어 supervisor 가 검수 반려와 같은 방식으로 처리하게 한다
    raise NotImplementedError("TODO를 완성하세요")
