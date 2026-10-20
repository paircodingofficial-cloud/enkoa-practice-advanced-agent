"""설정 층: rails/ 의 층 목록과 흐름이 맞는지, Settings 가 .env 규칙대로 값을 읽는지 확인한다."""
import pytest
import yaml
from pydantic import ValidationError

from app.core import config
from app.core.config import Settings


def test_guard_flows_are_defined_in_colang():
    # config.yml 의 flows 에 흐름 이름을 잘못 적으면 NeMo 가 그 층을 찾지 못한다. 고친 뒤 여기서 잡는다
    guard_config = yaml.safe_load((config.RAILS_DIR / "config.yml").read_text(encoding="utf-8"))
    colang = (config.RAILS_DIR / "rails.co").read_text(encoding="utf-8")
    flows = guard_config["rails"]["input"]["flows"] + guard_config["rails"]["output"]["flows"]
    for flow in flows:
        assert f"define subflow {flow}" in colang
    # 검색 결과 검사는 실행 레일(check_tool_result)이 맡으므로 NeMo 검색 레일은 두지 않는다
    assert "retrieval" not in guard_config["rails"]


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


def test_security_lists_stay_in_code():
    # 승인 도구와 역할 도구는 보안 규칙이라 .env 로 바꿀 수 있는 Settings 필드가 아니다
    assert "approval_tools" not in Settings.model_fields
    assert "role_tools" not in Settings.model_fields
    assert config.APPROVAL_TOOLS == ["cancel_ticket", "request_goods_refund"]
