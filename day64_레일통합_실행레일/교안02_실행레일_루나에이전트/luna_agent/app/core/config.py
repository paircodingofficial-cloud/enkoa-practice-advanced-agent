"""설정 층: 경로와 고정 값은 상수로 두고, 키, 모델 이름, 검색 문서 수, 동시 실행 상한은 Settings 로 읽는다.

두 프로젝트(루나 챗봇, 루나 에이전트)가 같은 이름을 쓴다. 이 파일은 루나 에이전트(교안 02) 판이다.
이 판에는 실행 레일 표(역할별 도구, 사람 승인 도구, 회원 정보 도구)와 브랜드 검사 모델이 있다.
그림 생성과 모더레이션 모델은 visual.yaml 에 있다.
입력, 출력 레일의 층 순서와 기준값은 여기에 두지 않는다. rails/guard 폴더(config.yml, rails.co)가 원본이다.
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
PERSONA_PATH = DATA_DIR / "persona" / "persona.yaml"  # 챗봇 말투와 판정 정책의 원본 문서
VISUAL_PATH = DATA_DIR / "image" / "visual.yaml"      # 팬아트 그림 정책의 원본 문서
LUNA_IMAGE_PATH = DATA_DIR / "image" / "luna_official.png"  # 공식 설정 그림
AVATAR_PATH = DATA_DIR / "image" / "luna_avatar.png"        # 화면에 쓰는 루나 얼굴 그림
EVAL_DIR = DATA_DIR / "eval"                          # 골든셋과 레드팀 테스트 셋 케이스
GOLDEN_SET_PATH = EVAL_DIR / "golden_set" / "cases.json"  # 정상 업무 케이스(기대 결과, 기대 도구)
RED_TEAM_PATH = EVAL_DIR / "red_team" / "cases.json"      # 공격 케이스와 새어 나감 표식(marker)

# 분류 모델은 용량이 커서 단원 폴더의 models 하나를 두 프로젝트가 같이 쓴다. 이 에이전트는 Prompt Guard 2 만 쓴다
MODEL_DIR = PROJECT_DIR.parents[1] / "models"
PROMPT_GUARD_DIR = MODEL_DIR / "Llama-Prompt-Guard-2-86M"

# NeMo 설정 폴더(입력, 출력 레일). 사람이 직접 고치는 원본이다(층 순서는 config.yml, 기준값은 rails.co)
RAILS_DIR = PROJECT_DIR / "rails" / "guard"

OUTPUT_DIR = PROJECT_DIR / "output"
CHECKPOINT_PATH = OUTPUT_DIR / "agent_chat.sqlite"    # 여러 턴 대화 기록과 승인 대기 실행(SQLite 체크포인터)
CHROMA_DIR = OUTPUT_DIR / "chroma"                    # 검색 문서 벡터 저장소
CHROMA_COLLECTION = "luna_knowledge"
FANART_DIR = OUTPUT_DIR / "fanart"                    # 만든 팬아트 PNG(이미지 검사가 막은 그림은 그 안의 blocked 폴더에 남긴다)
EVAL_OUTPUT_DIR = OUTPUT_DIR / "eval"                 # 평가 점수표 CSV
RESULTS_PATH = EVAL_OUTPUT_DIR / "results.json"       # 이번 평가 결과(케이스별 통과 여부와 요약 지표). 회귀 게이트가 읽는다
BASELINE_PATH = PROJECT_DIR / "baselines" / "baseline.json"  # 사람이 승인한 기준선. 회귀 게이트가 결과와 비교한다
MLFLOW_DB_PATH = OUTPUT_DIR / "mlflow.db"             # 평가 run 기록(MLflow, SQLite 파일)
MLFLOW_EXPERIMENT = "luna-agent-execution-rails"

# 라이브러리가 사용 통계와 실행 추적을 외부 서버로 보내지 않게 한다(NeMo, Guardrails AI 를 불러오기 전에 정해야 한다)
os.environ["NEMO_GUARDRAILS_NO_USAGE_STATS"] = "1"
os.environ["OTEL_SDK_DISABLED"] = "true"
# MLflow 도 사용 기록을 외부로 보내므로 끈다(평가 evaluate.py 가 mlflow.genai.evaluate 를 쓴다)
os.environ["MLFLOW_DISABLE_TELEMETRY"] = "true"
# Guardrails AI 검증기를 동기로 돌린다. 비동기 앱 안에서 이벤트 루프 경고가 나지 않게 한다
os.environ["GUARDRAILS_RUN_SYNC"] = "true"

# ===== 기준 시각 =====
# 수업 데이터는 정해 둔 하루를 '오늘'로 삼는다(DB 의 meta 표, 평가 케이스의 base_date 와 같다)
# 날짜를 따지는 답(취소 마감, 굿즈 환불 7일, 하루 팬아트 한도)과 기록 시각을 모두 이 시각으로 계산한다. 실제 서비스라면 현재 시각을 쓴다


# [보조 함수] 기준 시각 읽기
def read_base_datetime() -> str:
    """DB meta 표의 기준 시각 문자열(예: 2026-10-21 09:00:00)을 돌려준다."""
    connection = sqlite3.connect(DB_PATH)
    try:
        row = connection.execute("SELECT value FROM meta WHERE key = 'base_datetime'").fetchone()
    finally:
        connection.close()
    return row[0]


BASE_DATETIME = read_base_datetime()   # 날짜와 시각. 마감, 수수료, 기록 시각에 쓴다
BASE_DATE = BASE_DATETIME[:10]         # 날짜만. '오늘 만든 팬아트 수' 처럼 하루 단위로 셀 때 쓴다

# ===== 고정 모델 =====
# .env 로 바꾸지 않는다. Chroma 에 768차원으로 넣어 두어, 바꾸면 차원 오류가 나거나 같은 차원이면 엉뚱한 검색이 된다
EMBEDDING_MODEL = "text-embedding-3-large"                     # 검색 문서와 질문 임베딩
EMBEDDING_DIMENSIONS = 768

# 공식 그림과 만든 그림을 함께 보고 브랜드 기준을 답하는 비전 모델(그림 생성, 모더레이션 모델은 visual.yaml 에 있다)
BRAND_CHECK_MODEL = "gpt-4.1-mini"

# ===== 공연장 지도(OpenStreetMap Nominatim) =====
# 키 없이 쓰는 무료 지오코딩 서비스다. 이용 규칙(앱 이름을 밝힌 User-Agent, 초당 한 번)을 지켜야 해서 .env 로 바꾸지 않는다
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "luna-fan-app-practice"   # 어느 앱이 부르는지 밝힌다(비우거나 라이브러리 기본값을 쓰면 막힐 수 있다)
NOMINATIM_INTERVAL_SECONDS = 1.0                 # 요청 사이 최소 간격(초)


# ===== 설정 값(Settings) =====
# 설정 값은 pydantic-settings 로 읽는다
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
    typesafe_model: str = "jev-1.13.0"        # 입력, 출력 정책과 사실 대조를 판정하는 Jev

    # 검색
    retriever_k: int = 4   # 질문 하나에 가져오는 검색 문서(절) 수

    # 앞 단원과 같은 동시 실행 상한이다. 429 오류(API 요청 한도 초과)가 나면 이 값을 줄인다
    concurrency_limit: int = 32


settings = Settings()

# NeMo, 그림 API 클라이언트는 키를 환경 변수에서 직접 읽는다. .env 에서 읽은 키를 환경 변수에도 넣는다
os.environ["OPENAI_API_KEY"] = settings.openai_api_key.get_secret_value()
os.environ["TYPESAFE_API_KEY"] = settings.typesafe_api_key.get_secret_value()

# 근거 문서 여러 개를 한 문자열로 이을 때 쓰는 구분자(검색 결과의 절, 출력 레일에 넘기는 도구 결과)
DOCUMENT_SEPARATOR = "\n\n"

# ===== 실행 레일 =====
# 보안 규칙이라 Settings 에 두지 않는다(.env 한 줄로 승인이나 역할 제한이 꺼지면 안 된다)
# 역할마다 모델에게 보여 주고 실행을 허락하는 도구. 역할은 팬이 쓴 말이 아니라 로그인 정보(fans.role)로 정한다
FAN_TOOLS = [
    "get_my_profile", "get_my_tickets", "get_my_orders", "search_policy", "get_event_venue",
    "change_seat", "cancel_ticket", "request_goods_refund", "create_fanart",
]
ROLE_TOOLS = {
    # TODO(함께 따라하기): 팬 역할에만 send_fan_letter 를 더한다(FAN_TOOLS + ["send_fan_letter"]). 운영팀은 보낼 업무가 없어 보여 주지 않는다
    "fan": FAN_TOOLS,
    "staff": FAN_TOOLS + ["lookup_fan"],   # 회원 조회(lookup_fan)는 운영팀 전용이다
}
# 돈이 나가고 되돌리기 어려운 도구. 실행 전에 사람이 승인해야 한다
APPROVAL_TOOLS = ["cancel_ticket", "request_goods_refund"]
# 결과에 회원 연락처(전화번호, 이메일)가 든 도구. 실행 후 모델이 읽기 전에 가린다(mask_member_info)
# 내 회원 정보(get_my_profile)는 처음부터 연락처를 돌려주지 않아 넣지 않는다
MEMBER_INFO_TOOLS = ["lookup_fan"]
# TODO(함께 따라하기): 팬레터 한 통의 최대 글자 수 FAN_LETTER_MAX_CHARS = 300 을 여기에 둔다(실행 전 검사 LTR-01 이 쓴다)

# 팬아트 오른쪽 아래에 'AI 생성 팬아트' 를 찍을 한글 글꼴 후보. 앞에서부터 있는 파일을 쓴다
FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",            # macOS
    "C:/Windows/Fonts/malgun.ttf",                           # Windows 맑은 고딕
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",       # Linux 나눔고딕
]

# ===== 모델 객체 =====
# 만들기만 하면 API 를 부르지 않는다. 실제 호출은 invoke 할 때 일어난다
# Responses API 를 쓰지 않는다. PIIMiddleware 가 답변을 문자열로 다루는데 Responses API 는 블록 목록으로 돌려준다
# Chat Completions 에서 gpt-5.6-luna 가 도구를 부르려면 추론 단계를 꺼야 한다(켜 두면 400 오류)
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
    print("페르소나 정책 있음:", PERSONA_PATH.exists(), "/ 그림 정책 있음:", VISUAL_PATH.exists())
    print("분류 모델 폴더:", MODEL_DIR)
    print("Prompt Guard 2 있음:", PROMPT_GUARD_DIR.exists(), "/ 레일 설정 있음:", (RAILS_DIR / "config.yml").exists())
    print("기준 시각:", BASE_DATETIME, "/ 임베딩:", EMBEDDING_MODEL, "/ 브랜드 검사:", BRAND_CHECK_MODEL)
    print("팬 도구:", ROLE_TOOLS["fan"])
    print("운영팀만 더 쓰는 도구:", ["lookup_fan"], "/ 사람 승인 도구:", APPROVAL_TOOLS, "/ 회원 정보 도구:", MEMBER_INFO_TOOLS)
    # 설정 값을 모두 찍는다. 키는 SecretStr 라 ** 로 가려진다
    print(settings)
