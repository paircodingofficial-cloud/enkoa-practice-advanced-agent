"""설정 층: 모든 층이 함께 쓰는 경로, 고정 값, 설정 값(Settings), 모델 객체를 둔다.

경로와 바꾸지 않는 값은 상수로 두고, 키, 모델 이름, 검색 문서 수, 동시 실행 상한은 .env 로 바꿀 수 있게 Settings 로 읽는다.
레일 층 순서와 판정 기준값은 여기 두지 않는다. rails/guard 폴더가 원본이고 앱이 시작할 때 읽는다.
"""
import os
import sqlite3
from pathlib import Path

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# ===== 경로 =====
# app/core/config.py 에서 두 단계 위가 프로젝트 폴더다. 데이터와 산출물은 모두 이 폴더 기준이다
PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "luna_fan.db"                    # 팬, 공연, 티켓, 주문이 든 SQLite 파일
KNOWLEDGE_DIR = DATA_DIR / "knowledge"                # 검색 문서(공지, 규정) 마크다운 폴더
PERSONA_PATH = DATA_DIR / "persona" / "persona.yaml"  # 시스템 프롬프트와 판정 정책 글의 원본 문서
AVATAR_PATH = DATA_DIR / "image" / "luna_avatar.png"  # 화면에 쓰는 루나 얼굴 그림
EVAL_DIR = DATA_DIR / "eval"                          # 골든셋과 레드팀 케이스
GOLDEN_SET_PATH = EVAL_DIR / "golden_set" / "cases.json"  # 정상, 경계 질문과 정답 답변
RED_TEAM_PATH = EVAL_DIR / "red_team" / "cases.json"      # 공격 질문과 새어 나감 표식(marker)

# 분류 모델(Prompt Guard 2, Llama Guard 3)은 용량이 커서 단원 폴더의 models 하나를 두 프로젝트가 같이 쓴다
MODEL_DIR = PROJECT_DIR.parents[1] / "models"
PROMPT_GUARD_DIR = MODEL_DIR / "Llama-Prompt-Guard-2-86M"
LLAMA_GUARD_DIR = MODEL_DIR / "Llama-Guard-3-1B"

# NeMo 설정 폴더(직접 고치는 원본): 입력, 출력 레일. 층 순서는 config.yml 의 flows, 기준값은 rails.co 에 있다
RAILS_DIR = PROJECT_DIR / "rails" / "guard"

OUTPUT_DIR = PROJECT_DIR / "output"
CHECKPOINT_PATH = OUTPUT_DIR / "chat.sqlite"          # 여러 턴 대화 기록(SQLite 체크포인터)
CHROMA_DIR = OUTPUT_DIR / "chroma"                    # 검색 문서 벡터 저장소
CHROMA_COLLECTION = "luna_knowledge"
EVAL_OUTPUT_DIR = OUTPUT_DIR / "eval"                 # 평가 결과 CSV
RESULTS_PATH = EVAL_OUTPUT_DIR / "results.json"       # 회귀 게이트가 읽는 이번 평가 결과(gate/ 의 pytest)
BASELINE_PATH = PROJECT_DIR / "baselines" / "baseline.json"  # 사람이 승인한 기준선(회귀 게이트가 비교한다)
MLFLOW_DB_PATH = OUTPUT_DIR / "mlflow.db"             # 평가 run 기록(MLflow, SQLite 파일)
MLFLOW_EXPERIMENT = "luna-chatbot-rails"

# 라이브러리가 사용 통계와 실행 추적을 외부 서버로 보내지 않게 한다(NeMo, Guardrails AI 를 불러오기 전에 정해야 한다)
os.environ["NEMO_GUARDRAILS_NO_USAGE_STATS"] = "1"
os.environ["OTEL_SDK_DISABLED"] = "true"
# MLflow 도 사용 기록을 외부로 보내므로 끈다(평가 evaluate.py 가 mlflow.genai.evaluate 를 쓴다)
os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
# Guardrails AI 검증기를 동기로 돌린다. 비동기 앱 안에서 이벤트 루프 경고가 나지 않게 한다
os.environ["GUARDRAILS_RUN_SYNC"] = "true"

# ===== 기준 시각 =====
# 수업 데이터는 정해 둔 하루를 '오늘'로 삼는다(DB 의 meta 표, 평가 케이스의 base_date 와 같다)
# 날짜를 따지는 답(취소 마감, 굿즈 환불 7일)을 모두 이 시각으로 계산한다. 실제 서비스라면 현재 시각을 쓴다


# [보조 함수] 기준 시각 읽기
def read_base_datetime() -> str:
    """DB meta 표의 기준 시각 문자열(예: 2026-10-21 09:00:00)을 돌려준다."""
    # 읽기만 하고, 오류가 나도 연결은 닫는다
    connection = sqlite3.connect(DB_PATH)
    try:
        row = connection.execute("SELECT value FROM meta WHERE key = 'base_datetime'").fetchone()
    finally:
        connection.close()
    return row[0]


BASE_DATETIME = read_base_datetime()   # 답변 모델과 사실 대조가 받는 '지금'(core/prompts.py 의 BASE_TIME_TEXT)

# ===== 고정 모델 =====
# .env 로 바꾸지 않는다. Chroma 에 768차원으로 넣어 두어, 바꾸면 차원 오류가 나거나 같은 차원이면 엉뚱한 검색이 된다
EMBEDDING_MODEL = "text-embedding-3-large"                     # 검색 문서와 질문 임베딩
EMBEDDING_DIMENSIONS = 768

# ===== 공연장 지도(OpenStreetMap Nominatim) =====
# 키 없이 쓰는 무료 지오코딩 서비스다. 이용 규칙(앱 이름을 밝힌 User-Agent, 초당 한 번)을 지켜야 해서 .env 로 바꾸지 않는다
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "luna-fan-app-practice"   # 어느 앱이 부르는지 밝힌다(비우거나 라이브러리 기본값을 쓰면 막힐 수 있다)
NOMINATIM_INTERVAL_SECONDS = 1.0                 # 요청 사이 최소 간격(초)


# ===== 설정 값(Settings) =====
# 설정 값은 pydantic-settings 로 읽는다(아래 세 가지 때문이다)
# 1. 키가 없거나 형식이 틀리면(예: CONCURRENCY_LIMIT=abc) 앱이 시작할 때 바로 오류가 난다
# 2. .env 와 터미널 환경 변수가 같은 규칙으로 필드를 덮어쓴다(필드 이름을 대문자로 쓴 것이 변수 이름, 환경 변수가 .env 보다 먼저)
# 3. 테스트는 Settings(openai_api_key="test", ...) 처럼 다른 값으로 설정을 따로 만든다
class Settings(BaseSettings):
    """프로젝트 폴더의 .env 와 환경 변수에서 읽는 설정 값."""

    # 프로젝트 폴더의 .env 만 읽는다(다른 폴더의 .env 가 섞여 들어오지 않게 경로를 직접 준다)
    # extra="ignore": .env 에 여기 없는 이름이 있어도 오류를 내지 않는다
    # env_ignore_empty=True: OPENAI_CHAT_MODEL= 처럼 비워 둔 값은 없는 것으로 보고 기본값을 쓴다
    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
    )

    # 키: 기본값이 없어 비어 있으면 시작할 때 오류가 난다. print 하면 ** 로 가려진다
    openai_api_key: SecretStr
    typesafe_api_key: SecretStr

    # 모델 이름
    openai_chat_model: str = "gpt-5.6-luna"   # 답변 모델
    openai_eval_model: str = "gpt-4.1-mini"   # DeepEval 판사 모델(답변 모델과 다른 모델로 채점한다)
    typesafe_model: str = "jev-1.13.0"        # 입력, 출력 정책과 사실 대조를 판정하는 Jev

    # 검색
    retriever_k: int = 4   # 질문 하나에 가져오는 검색 문서(절) 수

    # 앞 단원과 같은 동시 실행 상한이다. 429 오류(API 요청 한도 초과)가 나면 이 값을 줄인다
    concurrency_limit: int = 32


settings = Settings()

# NeMo, DeepEval, Jev 클라이언트는 키를 환경 변수에서 직접 읽는다. .env 에서 읽은 키를 환경 변수에도 넣는다
os.environ["OPENAI_API_KEY"] = settings.openai_api_key.get_secret_value()
os.environ["TYPESAFE_API_KEY"] = settings.typesafe_api_key.get_secret_value()

# ===== 대화 기준 =====
# 공연을 콕 집지 않은 공연장 질문("팬미팅 장소 어디예요?")이 가리키는 공연. 화면 머리의 공지 줄도 이 공연이다
MAIN_EVENT_ID = "E01"

# 검색 문서 여러 개를 한 문자열로 이을 때 쓰는 구분자(답변 모델과 사실 대조 층이 받는 근거 글)
DOCUMENT_SEPARATOR = "\n\n"

# 라우터, 검색어 다시 쓰기, 답변 모델에 넘기는 최근 메시지 수(팬, 루나 메시지를 합친 수)
# 같은 대화 ID 로 계속 이어지면 기록이 끝없이 길어지므로 최근 세 턴만 넘긴다. 입력 레일(Jev)도 앞선 팬 메시지 두 개만 본다
RECENT_MESSAGES = 6

# ===== 모델 객체 =====
# 만들기만 하면 API 를 부르지 않는다. 실제 호출은 invoke 할 때 일어난다
# 팬 상담 답은 짧은 안내라 추론 단계를 끄고(reasoning_effort="none") 답이 빨리 나오게 한다
llm = ChatOpenAI(model=settings.openai_chat_model, reasoning_effort="none")

# 검색 문서와 질문을 같은 모델, 차원으로 임베딩한다
# check_embedding_ctx_length=False: 입력 길이를 미리 재서 나누는 자동 처리를 끈다(문서가 모두 짧다)
embedding_model = OpenAIEmbeddings(
    model=EMBEDDING_MODEL,
    dimensions=EMBEDDING_DIMENSIONS,
    check_embedding_ctx_length=False,
)


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.core.config
    print("프로젝트 폴더:", PROJECT_DIR)
    print("DB 파일 있음:", DB_PATH.exists(), "/ 검색 문서 폴더 있음:", KNOWLEDGE_DIR.exists())
    print("페르소나 정책 있음:", PERSONA_PATH.exists(), "/ 루나 얼굴 그림 있음:", AVATAR_PATH.exists())
    print("분류 모델 폴더:", MODEL_DIR)
    print("Prompt Guard 2 있음:", PROMPT_GUARD_DIR.exists(), "/ Llama Guard 3 있음:", LLAMA_GUARD_DIR.exists())
    print("레일 설정 있음:", (RAILS_DIR / "config.yml").exists())
    print("기준 시각:", BASE_DATETIME, "/ 대표 공연:", MAIN_EVENT_ID, "/ 임베딩:", EMBEDDING_MODEL)
    # 설정 값을 모두 찍는다. 키는 SecretStr 라 ** 로 가려진다
    print(settings)
