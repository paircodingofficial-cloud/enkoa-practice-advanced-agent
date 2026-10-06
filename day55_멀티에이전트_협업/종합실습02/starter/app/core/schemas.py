"""스키마 층: planner, researcher, synthesizer, supervisor 가 받는 구조화 출력의 모양을 정한다."""
from typing import Literal

from pydantic import BaseModel, Field


# planner 출력: 조사 작업 하나와 그 목록인 조사 계획.
class ResearchTask(BaseModel):
    """조사 작업 하나. task_id 는 planner 코드가 붙인다."""
    source: Literal["naver", "youtube", "web"] = Field(description="조사할 자료원 종류")
    query: str = Field(description="검색에 그대로 넣을 짧은 검색어")
    angle: str = Field(description="이 조사로 알아낼 것 한 문장")


class ResearchPlan(BaseModel):
    """planner 가 내는 조사 계획."""
    tasks: list[ResearchTask] = Field(description="조사 작업 목록")


# researcher 출력: 출처, 핵심 사실, 그 둘을 담은 조사 결과 한 건.
class Source(BaseModel):
    """출처 한 건."""
    title: str
    url: str
    date: str = Field(description="게시일 YYYY-MM-DD, 모르면 빈 문자열")


class KeyPoint(BaseModel):
    """핵심 사실 한 건과 그 사실이 나온 출처 URL."""
    fact: str = Field(description="글에 쓸 만한 핵심 사실 한 문장")
    url: str = Field(description="이 사실이 나온 출처의 URL. sources 에 넣은 URL 중 하나")


class Finding(BaseModel):
    """researcher 한 명의 조사 결과."""
    summary: str = Field(description="조사 결과 요약 3~4문장")
    # 사실과 출처를 따로 두면 작성자가 엉뚱한 출처를 붙인다. 사실마다 URL 을 묶는다.
    key_points: list[KeyPoint] = Field(description="핵심 사실과 그 사실이 나온 URL")
    sources: list[Source] = Field(description="도구 결과에서 실제로 확인한 출처만")


# synthesizer 출력: 작성자에게 넘길 브리프.
class Brief(BaseModel):
    """synthesizer 가 내는 작성용 브리프."""
    common_flow: str = Field(description="경쟁 콘텐츠들이 공통으로 다루는 흐름")
    content_gaps: list[str] = Field(description="경쟁 콘텐츠가 다루지 않은 내용")
    angles: list[str] = Field(description="블로그와 쇼츠에 추천하는 각도")
    gaps: list[str] = Field(description="글을 쓰기 전에 더 조사해야 할 사실, 없으면 빈 목록")


# supervisor 출력: 반려 뒤 누구에게 무엇을 시킬지.
class ReworkStep(BaseModel):
    """검수 반려 뒤 supervisor 가 정하는 다음 담당과 그 담당에게 줄 지시문."""
    next: Literal["writer", "planner"] = Field(
        description="writer: 지금 조사 결과로 고쳐 쓸 수 있음. planner: 조사 결과에 없는 정보를 더 조사해야 함"
    )
    instruction: str = Field(description="그 담당이 바로 할 일. 검수 피드백을 구체 작업으로 바꾼 지시문")
