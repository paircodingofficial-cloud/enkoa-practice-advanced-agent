"""도구 층: 작성자 에이전트가 제어권을 넘기는 핸드오프 도구(검수자에게 검수 요청, supervisor 에게 추가 조사 요청)."""
from langchain.tools import tool
from langgraph.types import Command


# [핸드오프 도구] 검수 요청: 다 쓴 초안의 파일 경로를 reviewer 에게 넘긴다.
@tool
def request_review(blog_path: str, shorts_path: str) -> Command:
    """블로그 글과 쇼츠 대본을 다 썼을 때 두 파일의 경로를 검수자(reviewer)에게 넘깁니다."""
    # TODO: 부모 그래프의 reviewer 로 넘어가는 핸드오프 Command 만들기
    # 1) goto 는 reviewer, graph 는 Command.PARENT 로 정한다. PARENT 가 에이전트 안이 아니라 바깥 그래프로 이동하게 한다
    # 2) update 는 바깥 State 에 반영되므로 reviewer 가 읽는 draft 필드만 채운다(블로그와 쇼츠 경로 두 개)
    raise NotImplementedError("TODO를 완성하세요")


# [핸드오프 도구] 추가 조사 요청: 빠진 자료를 적어 supervisor 에게 넘긴다.
@tool
def request_research(missing: str) -> Command:
    """브리프만으로 글을 쓸 수 없을 때 무엇이 빠졌는지 알리고 추가 조사를 요청합니다."""
    # planner 로 바로 가지 않고 supervisor 를 거쳐야 돌려보낸 횟수 상한 검사를 건너뛰지 않는다.
    # review 에 반려({"passed": False})를, feedback 에 빠진 자료를 실어 supervisor 가 검수 반려와 같은 방식으로 처리하게 한다.
    return Command(
        goto="supervisor",
        graph=Command.PARENT,
        update={"review": {"passed": False}, "feedback": missing},
    )
