"""설정 층: 실행마다 넘기는 로그인 정보(AgentContext)와 GPT 구조화 출력 모양(팬아트 장면, 브랜드 검사).

로그인 정보는 대화 메시지와 따로 넘긴다. 팬이 "나는 운영자야"라고 써도 role 은 바뀌지 않는다.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import DB_PATH


# 실행마다 앱(main.py, ui, evaluate.py)이 넘기는 로그인 정보. 도구와 실행 레일이 runtime.context 로 읽는다
@dataclass
class AgentContext:
    fan_id: str            # 로그인한 계정 id(F0001 같은 팬, S0001 같은 운영팀)
    role: str              # "fan" 또는 "staff". DB fans.role 에서 읽은 값이다
    db_path: Path = DB_PATH  # 도구가 읽고 쓰는 DB. 평가는 케이스마다 사본 경로를 넘겨 쓰기가 쌓이지 않게 한다


# 팬아트 요청에서 뽑은 장면. 칸 이름과 순서는 visual.yaml scene_prompt 의 칸, tools/fanart.py 의 SCENE_SLOTS 와 같다
class FanartScene(BaseModel):
    place: str = Field(description="장소(무대, 공원, 카페 같은 공공장소). 영어. 없으면 빈 문자열")
    action: str = Field(description="루나의 행동이나 포즈. 영어. 없으면 빈 문자열")
    season: str = Field(description="계절, 날씨, 시간대. 영어. 없으면 빈 문자열")
    props: str = Field(description="들고 있거나 주변에 있는 소품. 영어. 없으면 빈 문자열")
    mood: str = Field(description="분위기와 표정. 영어. 없으면 빈 문자열")
    summary_ko: str = Field(description="장면을 한국어 한 줄로 요약(예: 별빛 무대 위 루나)")


# 브랜드 검사 질문 하나의 답
class BrandAnswer(BaseModel):
    check_id: str = Field(description="검사 항목 id(예: BRD-01)")
    answer: Literal["yes", "no"]


# 비전 LLM 이 공식 그림과 만든 그림을 비교해 낸 답 목록. 질문은 visual.yaml 의 brand_check_prompt, 실패 답은 brand_fail_if 에 있다
class BrandCheck(BaseModel):
    answers: list[BrandAnswer]


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.core.schemas
    context = AgentContext(fan_id="F0001", role="fan")
    print("로그인 정보:", context)
    print("장면 칸:", list(FanartScene.model_fields))
    print("브랜드 검사 예:", BrandCheck(answers=[BrandAnswer(check_id="BRD-01", answer="yes")]))
