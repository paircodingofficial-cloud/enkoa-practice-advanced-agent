"""스키마 층: 슈퍼바이저와 분석 계획이 GPT 구조화 출력으로 받는 모양을 정한다."""
from typing import Literal

from pydantic import BaseModel, Field


# 슈퍼바이저 출력: 다음 담당자와 지시문
class NextStep(BaseModel):
    """슈퍼바이저가 한 번에 정하는 다음 담당자와 지시문."""
    # next_worker 는 그래프의 노드 이름과 같아야 그대로 goto 에 쓸 수 있다.
    # report_writer 는 넣지 않는다. 보고서로 넘길지는 supervisor 의 if 문이 정한다.
    next_worker: Literal["analysis_planner", "doc_reader", "web_researcher"] = Field(
        description="다음에 일을 맡길 담당자 한 명. 데이터 분석은 analysis_planner")
    instruction: str = Field(
        description="그 담당자에게 줄 지시문 3~5문장. 비교 기간, 볼 지표나 문서, 돌려받을 수치를 적는다")


# 슈퍼바이저 출력: 검수 반려 뒤 다음 담당자와 지시문
class ReworkStep(BaseModel):
    """검수 반려나 추가 조사 요청 뒤 슈퍼바이저가 정하는 다음 담당자와 지시문."""
    next_worker: Literal["report_writer", "analysis_planner", "doc_reader", "web_researcher"] = Field(
        description="report_writer: 지금 팀 기록으로 고쳐 쓸 수 있음. 나머지: 팀 기록에 없는 근거를 더 조사해야 함")
    instruction: str = Field(description="그 담당자가 바로 할 일. 피드백을 구체 작업으로 바꾼 지시문")


# 분석 계획 출력: 채널별 분석 작업의 목록. task_id 는 코드가 채널로 만든다
class AnalysisTask(BaseModel):
    """분석 작업 하나. 채널 하나를 분석가 한 명이 맡는다."""
    channel: Literal["traffic", "search", "youtube", "social", "newsletter"] = Field(
        description="분석할 채널. traffic: DB 의 경로별 조회와 발행 편수, search: 검색 노출·클릭, "
                    "youtube: 영상 노출·클릭률, social: 소셜 유입, newsletter: 뉴스레터")
    question: str = Field(description="그 채널에서 확인할 것 한두 문장. 비교 기간과 볼 지표를 적는다")


class AnalysisPlan(BaseModel):
    """분석 계획 노드가 내는 분석 작업 목록."""
    tasks: list[AnalysisTask] = Field(description="분석 작업 목록. 같은 채널은 한 번만")
