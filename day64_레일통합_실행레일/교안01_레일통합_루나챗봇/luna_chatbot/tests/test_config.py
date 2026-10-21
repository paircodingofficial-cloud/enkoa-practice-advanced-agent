"""설정 층: 경로, 레일 설정 폴더(원본), 경로 후보, 기준 시각이 데이터와 맞는지, Settings 가 .env 규칙대로 값을 읽는지 확인한다."""
import json

import pytest
from nemoguardrails import RailsConfig
from pydantic import ValidationError

from app.core import config
from app.core.config import Settings
from app.core.prompts import ROUTES
from app.graph.edges import LOOKUP_NODES, ROUTE_NODES
from app.guards.actions import GUARD_ACTIONS


def test_data_files_exist():
    # 챗봇이 읽는 데이터 파일이 모두 프로젝트 안에 있다
    for path in [config.DB_PATH, config.PERSONA_PATH, config.AVATAR_PATH, config.GOLDEN_SET_PATH, config.RED_TEAM_PATH]:
        assert path.exists(), path
    assert len(list(config.KNOWLEDGE_DIR.glob("*.md"))) > 0


def test_model_dir_is_day_folder():
    # 분류 모델은 프로젝트가 아니라 단원(day64) 폴더의 models 에 있다
    assert config.MODEL_DIR.name == "models"
    assert config.MODEL_DIR.parent == config.PROJECT_DIR.parents[1]


def test_rails_folder_is_guard_only():
    # 레일 설정 폴더는 입력, 출력 레일(rails/guard) 하나다. 경로 고르기는 NeMo 가 아니라 앱의 라우터 노드가 한다
    assert (config.RAILS_DIR / "config.yml").exists()
    assert [path.name for path in config.RAILS_DIR.parent.iterdir() if path.is_dir()] == ["guard"]


def test_settings_defaults():
    settings = config.settings
    assert settings.retriever_k == 4
    assert settings.concurrency_limit == 32
    # 레일 층 순서와 기준값은 Settings 에 없다(rails/ 폴더가 원본이다). 키, 모델 이름, 검색 문서 수, 동시 실행 상한만 둔다
    assert sorted(Settings.model_fields) == ["concurrency_limit", "openai_api_key", "openai_chat_model", "openai_eval_model",
                                             "retriever_k", "typesafe_api_key", "typesafe_model"]


def test_base_date_matches_cases():
    # 기준 시각이 평가 케이스의 base_date 와 다르면 날짜를 따지는 정답 답변이 어긋난다(케이스는 T, DB 는 공백으로 날짜와 시각을 나눈다)
    for path in [config.GOLDEN_SET_PATH, config.RED_TEAM_PATH]:
        assert json.loads(path.read_text(encoding="utf-8"))["base_date"].replace("T", " ") == config.BASE_DATETIME


def test_route_names_match_graph_edges():
    # 라우터의 경로 후보(prompts.py)와 그래프가 다음 노드를 찾는 표(edges.py)의 이름이 같아야 한다
    assert sorted(ROUTES) == sorted(ROUTE_NODES)
    assert "rag" in ROUTES


def test_expected_routes_are_known_names():
    # 평가 케이스의 기대 경로는 라우터 후보이거나, 조회 노드가 바꾸는 로그인 안내(login)다
    known = set(ROUTES) | {"login"}
    assert "login" in LOOKUP_NODES
    checked = 0
    for path in [config.GOLDEN_SET_PATH, config.RED_TEAM_PATH]:
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            route = case["expected"]["route"]
            if route is None:
                continue
            checked += 1
            assert route in known, (case["case_id"], route)
    assert checked > 0


def test_guard_rails_have_no_models():
    # 앱은 판정만 받으므로 rails/guard 에 모델(답변 모델, 임베딩 모델)과 NeMo 봇용 프롬프트(prompts.yml)를 두지 않는다
    assert RailsConfig.from_path(str(config.RAILS_DIR)).models == []
    assert not (config.RAILS_DIR / "prompts.yml").exists()


def test_guard_rails_flows_have_subflows_and_actions():
    # config.yml 의 flows 목록에 적은 층마다 rails.co 에 같은 이름의 흐름이 있고, 흐름이 부르는 액션이 등록 목록에 있다
    # 이름을 잘못 적으면 NeMo 가 그 층을 찾지 못하므로, 원본 폴더를 손으로 고친 뒤 이 테스트로 확인한다
    guard_config = RailsConfig.from_path(str(config.RAILS_DIR))
    colang = (config.RAILS_DIR / "rails.co").read_text(encoding="utf-8")
    flows = guard_config.rails.input.flows + guard_config.rails.output.flows
    assert flows[:3] == ["prompt guard 2 input", "jev policy input", "llama guard 3 input"]
    for flow in flows:
        assert f"define subflow {flow}" in colang, flow

    action_names = []
    for action in GUARD_ACTIONS:
        action_names.append(action.__name__)
    for line in colang.splitlines():
        if "execute " in line and not line.strip().startswith("#"):
            called = line.split("execute ")[1].split("(")[0]
            assert called in action_names, called


def test_guard_rails_have_no_retrieval_rails():
    # 검색 레일은 NeMo 에 두지 않는다. 판정만 묻는 check_async 는 검색 레일을 돌리지 않으므로 그래프 노드가 맡는다
    assert RailsConfig.from_path(str(config.RAILS_DIR)).rails.retrieval.flows == []


def test_settings_fields_override_defaults():
    # 테스트용 설정은 .env 를 읽지 않고(_env_file=None) 다른 값으로 따로 만든다
    settings = Settings(_env_file=None, openai_api_key="test", typesafe_api_key="test", retriever_k=2)
    assert settings.retriever_k == 2
    assert settings.openai_chat_model == "gpt-5.6-luna"
    # 키는 print 해도 가려진다
    assert "test" not in str(settings)


def test_empty_env_value_uses_default(monkeypatch):
    # .env 에 OPENAI_CHAT_MODEL= 처럼 비워 두면 빈 문자열이 아니라 기본값을 쓴다(env_ignore_empty)
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "")
    assert Settings(_env_file=None).openai_chat_model == "gpt-5.6-luna"


def test_missing_key_or_bad_value_fails_at_start(monkeypatch):
    # 키가 비어 있거나 숫자 칸에 글자가 들어가면 만들 때 바로 오류가 난다
    monkeypatch.setenv("OPENAI_API_KEY", "")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("CONCURRENCY_LIMIT", "abc")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
