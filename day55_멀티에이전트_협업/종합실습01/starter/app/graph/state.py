"""그래프 층: 슈퍼바이저와 워커가 함께 쓰는 State, Send 입력, 분석 결과를 모으는 리듀서."""
import operator
from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


# [리듀서] task_id 별로 모으는 dict 병합
def merge_analyses(current: dict, new: dict) -> dict:
    """task_id 기준으로 합친 새 analyses 딕셔너리를 돌려준다."""
    # current(지금까지 모인 결과)를 직접 고치지 않도록 복사본을 만든다
    merged = dict(current)
    # 복사본에 new(분석가 한 명이 돌려준 {task_id: 결과})를 넣는다. 같은 task_id 는 새 값으로 덮인다
    merged.update(new)
    return merged


# [State] 콘텐츠 하락 원인 분석 팀 그래프의 공유 데이터
class TeamState(TypedDict):
    # 처음 설정: 노드에서 바꾸지 않는 입력
    request: str        # 사용자 요청
    run_dir: str        # 이번 실행의 산출물 폴더(프로젝트 기준 상대경로, 예: output/20261006_173507)

    # supervisor: 다음 담당자에게 넘길 값
    next_worker: str    # 슈퍼바이저가 고른 다음 담당자
    instruction: str    # 슈퍼바이저가 그 담당자에게 준 지시문
    turn: int           # 슈퍼바이저가 담당자에게 일을 맡긴 횟수(턴)
    round: int          # 반려(검수 반려, 추가 조사 요청)를 처리한 횟수(라운드)

    # analysis_planner: 이번에 병렬로 분석할 작업 목록 [{task_id, channel, question}, ...]
    plan: list[dict]

    # data_analyst: 병렬 분석가가 같은 단계에 동시에 쓰므로 리듀서가 꼭 필요하다(없으면 InvalidUpdateError).
    # task_id 를 키로 모아 같은 채널을 다시 분석하면 그 키의 값만 새 결과로 바뀌고 나머지는 남는다. 시작 State 의 analyses 도 이 리듀서를 거친다.
    analyses: Annotated[dict[str, dict], merge_analyses]   # {task_id: {channel, question, result}}

    # doc_reader, web_researcher: 새 보고 하나만 리스트로 돌려주면 operator.add 가 기존 보고 뒤에 이어 붙인다
    findings: Annotated[list[dict], operator.add]          # [{turn, worker, result}, ...]

    # report_writer, reviewer: 보고서 검수 흐름
    report_path: str    # 작성자가 핸드오프로 넘긴 보고서 파일 이름
    review: dict | None     # 아직 처리하지 않은 반려 판정(검수 반려, 추가 조사 요청). 없으면 None
    feedback: str       # 가장 최근 검수 피드백(또는 작성자의 추가 조사 요청 내용)

    # 기록: messages.json 에 남길 지시와 워커 대화. add_messages 가 새 메시지를 쌓는다
    messages: Annotated[list, add_messages]


# Send 는 State 전체 대신 이 작은 입력만 data_analyst 에 넘긴다.
class AnalysisInput(TypedDict):
    """Send 로 data_analyst 하나에 넘기는 입력."""
    task: dict          # {task_id, channel, question}
    run_dir: str        # 차트를 저장할 산출물 폴더
