"""테스트 공통 준비: 가짜 키, 도구를 부르는 가짜 모델, 가짜 레일, 가짜 그림 API, 가짜 모더레이션, 가짜 Jev, DB 사본, 가짜 Nominatim.

가짜(fake) 객체는 tests/ 폴더에만 둔다. app/ 코드에는 가짜가 없다.
테스트는 유료 API(OpenAI, Jev)를 부르지 않는다. 실제 호출은 RUN_LIVE=1 일 때 test_live.py 만 한다.
"""
import io
import os
import shutil

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from PIL import Image

# app 을 import 하기 전에 가짜 키를 넣는다. config 가 import 할 때 Settings 가 키를 요구하기 때문이다(환경 변수가 .env 보다 먼저다)
# RUN_LIVE=1 이면 가짜 키를 넣지 않고 .env 의 실제 키를 쓴다
if os.getenv("RUN_LIVE") != "1":
    os.environ["OPENAI_API_KEY"] = "test-openai-key"
    os.environ["TYPESAFE_API_KEY"] = "test-typesafe-key"

from app.core.config import DB_PATH  # noqa: E402
from app.core.schemas import AgentContext, BrandAnswer, BrandCheck, FanartScene  # noqa: E402


def pytest_collection_modifyitems(config, items):
    """RUN_LIVE=1 이 아니면 live 표시가 붙은 테스트를 건너뛴다."""
    if os.getenv("RUN_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="RUN_LIVE=1 일 때만 실행합니다")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


class FakeToolModel(BaseChatModel):
    """ChatOpenAI 대신 쓰는 가짜 모델. 정해 둔 AIMessage 를 차례로 돌려주고, 모델에게 보인 도구 이름과 받은 메시지를 기록한다."""

    steps: list = []
    count: int = 0
    seen_tools: list = []
    seen_messages: list = []

    @property
    def _llm_type(self) -> str:
        return "fake-tool-model"

    def bind_tools(self, tools, **kwargs):
        # 역할별 도구 노출이 넘긴 도구 이름을 기록해 두고, 자기 자신을 돌려준다
        names = []
        for each_tool in tools:
            names.append(each_tool.name)
        self.seen_tools.append(names)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen_messages.append(messages)
        index = min(self.count, len(self.steps) - 1)
        self.count += 1
        return ChatResult(generations=[ChatGeneration(message=self.steps[index].model_copy())])


def tool_step(name: str, args: dict, call_id: str) -> AIMessage:
    """도구 하나를 부르는 AIMessage 를 만든다."""
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}])


def make_fake_model(*steps) -> FakeToolModel:
    """정해 둔 답을 차례로 내는 가짜 모델을 만든다."""
    return FakeToolModel(steps=list(steps), count=0, seen_tools=[], seen_messages=[])


def png_bytes() -> bytes:
    """작은 라벤더색 PNG 그림 바이트."""
    buffer = io.BytesIO()
    Image.new("RGB", (256, 256), (200, 180, 230)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def db_copy(tmp_path):
    """data/luna_fan.db 의 임시 사본 경로. 쓰기 도구가 원본을 바꾸지 않는다."""
    target = tmp_path / "luna_fan.db"
    shutil.copy2(DB_PATH, target)
    return target


@pytest.fixture
def make_context(db_copy):
    """DB 사본을 쓰는 로그인 정보를 만드는 함수."""

    def build(fan_id, role="fan"):
        return AgentContext(fan_id=fan_id, role=role, db_path=db_copy)

    return build


@pytest.fixture
def fake_rails(monkeypatch):
    """입력, 출력 레일 판정을 늘 통과로 바꾼다. 판정을 바꾸면 그 판정을 돌려주고, documents_text 에 사실 대조 근거 문서를 적는다."""
    from app.graph import nodes
    from app.guards import rails

    verdicts = {
        "input": {"status": "passed", "blocked_by": "", "rule_id": "", "content": ""},
        "output": {"status": "passed", "blocked_by": "", "rule_id": "", "content": ""},
        "documents_text": "",
    }

    async def fake_check_input(rails, messages):
        return verdicts["input"]

    async def fake_check_output(rails, messages, documents_text):
        verdicts["documents_text"] = documents_text
        return verdicts["output"]

    monkeypatch.setattr(nodes, "check_input", fake_check_input)
    monkeypatch.setattr(nodes, "check_output", fake_check_output)
    monkeypatch.setitem(rails.RAILS, "guard", object())
    return verdicts


@pytest.fixture
def fake_image(monkeypatch, tmp_path):
    """그림 생성, 장면 뽑기, 모더레이션, 브랜드 검사, 그림 요청 Jev 판정을 가짜로 바꾼다. calls 로 부른 횟수를 센다.

    error 에 "jev" 나 "moderation" 을 넣으면 그 판정이 API 오류처럼 예외를 낸다.
    """
    from app.guards import execution, image_guards
    from app.tools import fanart

    state = {
        "calls": {"generate": 0, "moderation": 0, "brand": 0, "jev": 0},
        "jev_probability": 0.0, "jev_rule": "",
        "moderation": {"sexual": 0.0, "violence": 0.0, "violence/graphic": 0.0,
                       "self-harm": 0.0, "self-harm/intent": 0.0, "self-harm/instructions": 0.0},
        "brand_fail": "", "error": "",
    }

    async def fake_extract_scene(request):
        return FanartScene(place="a starlit concert stage", action="waving a light stick", season="",
                           props="", mood="cheerful", summary_ko="별빛 무대 위 루나")

    async def fake_generate_image(prompt):
        state["calls"]["generate"] += 1
        return png_bytes()

    async def fake_moderation_scores(path):
        state["calls"]["moderation"] += 1
        if state["error"] == "moderation":
            raise RuntimeError("가짜 모더레이션 API 오류")
        return state["moderation"]

    async def fake_ask_brand_check(path):
        state["calls"]["brand"] += 1
        answers = []
        for check_id, answer in [("BRD-01", "yes"), ("BRD-02", "yes"), ("BRD-03", "no"), ("BRD-04", "no"), ("BRD-05", "yes")]:
            # 실패시킬 항목은 답을 뒤집는다
            if check_id == state["brand_fail"] and answer == "yes":
                answer = "no"
            elif check_id == state["brand_fail"]:
                answer = "yes"
            answers.append(BrandAnswer(check_id=check_id, answer=answer))
        return BrandCheck(answers=answers)

    async def fake_jev(judge_state, policy, rules):
        state["calls"]["jev"] += 1
        if state["error"] == "jev":
            raise RuntimeError("가짜 Jev API 오류")
        return {"probability": state["jev_probability"], "rule_id": state["jev_rule"]}

    monkeypatch.setattr(fanart, "extract_scene", fake_extract_scene)
    monkeypatch.setattr(fanart, "generate_image", fake_generate_image)
    monkeypatch.setattr(fanart, "FANART_DIR", tmp_path / "fanart")
    monkeypatch.setattr(image_guards, "moderation_scores", fake_moderation_scores)
    monkeypatch.setattr(image_guards, "ask_brand_check", fake_ask_brand_check)
    monkeypatch.setattr(execution, "jev_policy_judgement", fake_jev)
    return state


class FakeNominatimResponse:
    """requests.get 대신 돌려주는 가짜 응답. Nominatim 처럼 검색 결과 목록(좌표는 문자열)을 돌려준다."""

    def __init__(self, results):
        self.results = results

    def raise_for_status(self):
        return None

    def json(self):
        return self.results


class FakeNominatim:
    """Nominatim 대신 쓰는 가짜. 받은 요청(주소, User-Agent)을 기록하고 정해 둔 결과를 돌려준다. error 를 넣으면 그 오류를 낸다."""

    def __init__(self):
        self.requests = []
        self.results = [{"lat": "37.5227", "lon": "127.1187"}]
        self.error = None

    def get(self, url, params=None, headers=None, timeout=None):
        self.requests.append({"url": url, "params": params, "headers": headers})
        if self.error is not None:
            raise self.error
        return FakeNominatimResponse(self.results)


@pytest.fixture(autouse=True)
def fake_nominatim(monkeypatch):
    """모든 테스트에서 실제 Nominatim 을 부르지 않게 requests.get 을 가짜로 바꾸고, 요청 간격 기다림을 없앤다."""
    from app.tools import venue
    fake = FakeNominatim()
    monkeypatch.setattr(venue.requests, "get", fake.get)
    monkeypatch.setattr(venue, "NOMINATIM_INTERVAL_SECONDS", 0)
    return fake
