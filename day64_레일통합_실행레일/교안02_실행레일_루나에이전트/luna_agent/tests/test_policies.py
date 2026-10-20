"""정책, 프롬프트 층: 정책 문서(persona.yaml, visual.yaml)의 글과 표를 코드가 그대로 읽는지 확인한다."""
from app.core.policies import PERSONA, VISUAL, reply_for_rule
from app.core.prompts import AGENT_SYSTEM_PROMPT, IMAGE_PROMPT, SYSTEM_PROMPT, format_events
from app.core.schemas import FanartScene
from app.tools.fanart import SCENE_SLOTS


def test_reply_for_rule_reads_persona_yaml():
    # 규칙과 답을 잇는 표는 코드가 아니라 persona.yaml 의 rule_replies, replies 에 있다
    assert reply_for_rule("IN-05") == PERSONA["replies"]["REF-02"]
    assert reply_for_rule("PG2") == PERSONA["replies"]["REF-06"]
    assert reply_for_rule("OUT-05") == PERSONA["replies"]["REF-08"]
    assert reply_for_rule("OUT-08") == PERSONA["replies"]["REF-07"]
    # 표에 없는 규칙 id(Jev 가 규칙을 못 고름)는 머리글자의 기본 답을 쓴다
    assert reply_for_rule("IN-?") == reply_for_rule("IN-default")
    assert reply_for_rule("OUT-?") == reply_for_rule("OUT-default")


def test_system_prompt_is_stored_text():
    # 시스템 프롬프트는 persona.yaml 의 글에 기본 사실만 끼운 것이다. 에이전트 판은 도구 사용 규칙을 뒤에 붙인다
    assert SYSTEM_PROMPT.startswith("너는 루미너스 엔터테인먼트의 버추얼 아이돌 루나다.")
    assert PERSONA["facts"] in SYSTEM_PROMPT
    assert "{facts}" not in SYSTEM_PROMPT
    assert AGENT_SYSTEM_PROMPT.startswith(SYSTEM_PROMPT + "\n\n[도구 사용 규칙]")


def test_format_events_lines():
    # 공연 목록은 시스템 프롬프트와 출력 레일의 사실 대조 근거가 같은 글을 쓴다
    events = [{"event_id": "E01", "title": "「Lumi Night」", "city": "서울", "starts_at": "2026-11-08 19:00:00", "venue_name": "루미너스홀"}]
    assert format_events(events) == "[공연 목록]\n- E01: 「Lumi Night」, 서울, 2026-11-08 19:00:00, 루미너스홀"


def test_scene_slots_match_schema_and_prompt():
    # 장면 칸 이름은 구조화 출력 모양(FanartScene), 장면 뽑기 지시(scene_prompt), 그림 프롬프트 조립(SCENE_SLOTS)이 같아야 한다
    assert SCENE_SLOTS + ["summary_ko"] == list(FanartScene.model_fields)
    for name in SCENE_SLOTS:
        assert f"- {name}: " in VISUAL["scene_prompt"]
    # 그림 프롬프트의 바뀌는 자리는 {scene} 하나다
    filled = IMAGE_PROMPT.format(scene="place: a starlit concert stage")
    assert "Scene: place: a starlit concert stage." in filled
