"""그래프 층: State, Send 입력, 실행 컨텍스트와 병렬 결과 리듀서를 정한다."""
from pathlib import Path
from typing import Annotated, Any

from typing_extensions import TypedDict


# [리듀서] task_id 별로 모으는 dict 병합
def merge_findings(current: dict, new: dict) -> dict:
    """task_id 기준으로 합친 새 findings 딕셔너리를 돌려준다."""
    # TODO: 병렬 researcher 결과를 task_id 기준으로 합치는 리듀서 만들기
    # 1) current(지금까지 모인 결과)를 직접 고치지 않도록 복사본을 만든다
    # 2) 복사본에 new(researcher 한 명이 돌려준 {task_id: 결과})를 넣는다. 같은 task_id 는 새 값으로 덮인다
    # 3) 합친 복사본을 돌려준다
    raise NotImplementedError("TODO를 완성하세요")


# [State] 콘텐츠 팀 그래프의 공유 데이터
class State(TypedDict):
    """부모 그래프의 State. messages 는 두지 않고 필요한 필드만 둔다."""
    request: str                                         # 사용자 요청
    report: str                                          # 분석 보고서 본문
    plan: list[dict]                                     # planner: 지금까지 계획한 조사 작업 전체
    # researcher: 병렬 researcher 가 같은 단계에 동시에 쓰므로 리듀서가 꼭 필요하다(없으면 InvalidUpdateError).
    # task_id 를 키로 모아 dispatch 가 이미 끝난 작업을 바로 찾는다. 추가 조사 작업도 planner 가 새 번호를 이어 붙여 키가 겹치지 않는다.
    findings: Annotated[dict[str, dict], merge_findings]
    brief: dict                                          # synthesizer: 종합 브리프
    round: int                                           # supervisor: 검수 반려 뒤 돌려보낸 횟수
    gap_filled: bool                                     # supervisor: 첫 초안 전 보충 조사를 이미 보냈는지
    draft: dict                                          # writer: 초안 파일 경로 {"blog": ..., "shorts": ...}
    review: dict | None                                  # reviewer: 검수 판정. supervisor 에서 값이 있으면 처리할 반려가 있다는 뜻
    feedback: str                                        # reviewer: 가장 최근 검수 피드백(또는 작성자의 추가 조사 요청)
    instruction: str                                     # supervisor: 반려 뒤 다음 담당에게 준 지시문


# Send 는 State 전체 대신 이 작은 입력만 researcher 에 넘긴다.
class ResearchInput(TypedDict):
    """Send 로 researcher 하나에 넘기는 입력."""
    task: dict


# 에이전트, 도구, 폴더처럼 실행 내내 그대로인 자원은 State 가 아니라 context 로 넘긴다.
class Context(TypedDict):
    """실행할 때 context 로 넘기는 값. State 에 넣지 않는 실행 자원이다."""
    tools: dict[str, list]   # 워커 이름 -> 허용된 MCP 도구
    run_dir: Path            # 이번 실행의 산출물 폴더
    writer: Any              # create_writer 가 만든 작성자 에이전트
