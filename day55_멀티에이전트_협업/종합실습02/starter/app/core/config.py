"""설정 층: 경로, 모델, 상한을 모으고 프로젝트 폴더의 .env 만 읽는다."""
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# 경로는 모두 프로젝트 폴더를 기준으로 잡는다.
PROJECT_DIR = Path(__file__).resolve().parents[2]   # 종합실습02/starter
DATA_DIR = PROJECT_DIR / "data"
OUTPUT_DIR = PROJECT_DIR / "output"
REPORT_PATH = DATA_DIR / "analysis_report.md"       # 종합실습01 에서 만든 분석 보고서 사본

# 다른 폴더의 .env 가 잡히지 않게 프로젝트 폴더의 .env 를 경로로 지정해 읽는다.
load_dotenv(PROJECT_DIR / ".env")

# 모델 이름. 환경변수에 값이 있으면 그 값을, 없으면 기본값을 쓴다.
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-5.6-luna")
TYPESAFE_MODEL = os.getenv("TYPESAFE_MODEL", "jev-1.13.0")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")

# 반복과 호출 상한. 비용이 늘거나 루프가 끝없이 도는 것을 막는다.
MAX_TASKS = 6          # 첫 계획의 조사 작업 수 상한
MAX_EXTRA_TASKS = 3    # 보충 조사 계획의 작업 수 상한
MAX_ROUNDS = 2         # 검수 반려 뒤 supervisor 가 돌려보낸 횟수 상한(첫 초안 전 보충 조사 1번은 세지 않는다)
TOOL_CALL_LIMIT = 4    # researcher 한 번의 도구 호출 상한. 넘으면 막고 답을 내게 한다
AGENT_CALL_LIMIT = 10  # 조사원, 작성자 에이전트 한 번 실행의 모델 호출 상한
PASS_SCORE = 2.0       # 검수 통과에 필요한 Jev Score(0~3) 최저값

# 이 모델은 Chat Completions 에서 도구 호출을 받지 않아 Responses API 로 부른다.
llm = ChatOpenAI(model=CHAT_MODEL, use_responses_api=True, timeout=120)

# 작성자용 모델. 한 응답에 도구를 하나만 부르게 한다. 핸드오프 도구 두 개를 한 번에 부르면 한쪽만 반영된다.
writer_llm = ChatOpenAI(model=CHAT_MODEL, use_responses_api=True, timeout=120,
                        model_kwargs={"parallel_tool_calls": False})
