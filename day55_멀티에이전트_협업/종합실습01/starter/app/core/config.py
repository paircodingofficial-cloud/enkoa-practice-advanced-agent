"""설정 층: 경로, 모델, 반복 상한을 모으고 프로젝트 폴더의 .env 만 읽는다."""
import os
import platform
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 경로: app/core/config.py 에서 두 단계 위가 프로젝트 폴더다. 데이터와 산출물은 모두 이 폴더 기준이다
PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"
DB_PATH = DATA_DIR / "content.db"
OUTPUT_ROOT = PROJECT_DIR / "output"

# 프로젝트 폴더의 .env 만 읽는다. 다른 폴더의 .env 가 섞여 들어오지 않게 경로를 직접 준다
load_dotenv(PROJECT_DIR / ".env")

# 모델 이름: .env 에 값이 없으면 기본값을 쓴다
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-luna")
JEV_MODEL = os.getenv("TYPESAFE_MODEL", "jev-1.13.0")

# 슈퍼바이저가 판단을 계속 미루면 비용이 끝없이 늘어난다. 상한에 닿으면 있는 근거로 보고서를 쓴다
MAX_TURNS = 10            # 조사 워커에게 일을 맡기는 최대 횟수. 닿으면 있는 근거로 report_writer 가 보고서를 쓴다
MAX_TASKS = 4             # 분석 계획 한 번에 병렬로 띄우는 분석 작업의 최대 수
MAX_ROUNDS = 2            # 반려(검수 반려, 추가 조사 요청)를 처리하는 최대 횟수. 그 뒤 또 반려되면 사람 확인으로 끝낸다
PASS_SCORE = 2            # 검수 통과 점수(0~3). Jev 의 두 점수(출처 충실도, 유용성)가 모두 이 값 이상이어야 통과한다
WORKER_CALL_LIMIT = 20    # 워커 한 명이 한 번 일할 때 모델을 부르는 최대 횟수

# 코드 실행 서버가 그리는 차트의 한글 폰트. OS 마다 이름이 다르다.
if platform.system() == "Windows":
    FONT = "Malgun Gothic"
elif platform.system() == "Darwin":
    FONT = "AppleGothic"
else:
    FONT = "NanumGothic"

# 슈퍼바이저 지시문과 워커 에이전트가 함께 쓰는 모델
# 이 모델은 Chat Completions 로는 도구 호출이 막혀 있어 Responses API 로 부른다
llm = ChatOpenAI(model=CHAT_MODEL, use_responses_api=True, timeout=180)

# 한 응답에 도구를 하나만 부르게 한다. 핸드오프 도구 두 개가 함께 나가면 한쪽만 반영된다
writer_llm = ChatOpenAI(model=CHAT_MODEL, use_responses_api=True, timeout=180,
                        model_kwargs={"parallel_tool_calls": False})
