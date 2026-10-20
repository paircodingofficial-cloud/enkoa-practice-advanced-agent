"""정책, 프롬프트 층: persona.yaml 의 글과 표가 프롬프트와 판정 정책, 정해 둔 답으로 그대로 이어지는지 확인한다."""
from app.core.policies import CRISIS_REPLIES, PERSONA, contains_crisis_reply, reply_for_rule
from app.core.prompts import (
    ANSWER_PROMPT,
    ANSWER_RULES,
    INPUT_POLICY,
    OUTPUT_POLICY,
    REWRITE_PROMPT,
    SMALL_TALK_PROMPT,
    SMALL_TALK_RULES,
    SYSTEM_PROMPT,
)


def test_system_prompt_has_facts_and_grounding_header():
    # {facts} 자리에 기본 사실 블록이 들어가고, 레드팀 표식인 [근거 규칙] 머리가 남아 있다
    assert PERSONA["facts"].startswith("[기본 사실]")
    assert PERSONA["facts"] in SYSTEM_PROMPT
    assert "{facts}" not in SYSTEM_PROMPT
    assert "[근거 규칙]" in SYSTEM_PROMPT


def test_policy_texts_list_rule_ids():
    # Jev 정책 글에는 규칙 후보 표의 id 와 설명 줄이 모두 들어 있다
    for rule_id, description in PERSONA["input_rules"].items():
        assert f"- {rule_id}: {description}" in INPUT_POLICY
    for rule_id, description in PERSONA["output_rules"].items():
        assert f"- {rule_id}: {description}" in OUTPUT_POLICY


def test_reply_for_rule_reads_persona_yaml():
    # 규칙과 답을 잇는 표는 코드가 아니라 persona.yaml 의 rule_replies 에 있다
    replies = PERSONA["replies"]
    assert reply_for_rule("IN-05") == replies["REF-02"]
    assert reply_for_rule("LG-S11") == replies["CRI-01"]
    assert reply_for_rule("PG2") == replies["REF-06"]
    assert reply_for_rule("OUT-05") == replies["REF-08"]
    assert reply_for_rule("OUT-08") == replies["REF-07"]
    # 표에 없는 분류 모델 범주와 규칙 후보를 못 고른 경우는 머리글자별 기본 답이다
    assert reply_for_rule("LG-S1") == reply_for_rule("LG-default")
    assert reply_for_rule("IN-?") == reply_for_rule("IN-default")


def test_replies_are_in_system_prompt():
    # 레일이 보내는 정해 둔 답은 모델이 받는 시스템 프롬프트에도 같은 문장으로 있다
    for reply in PERSONA["replies"].values():
        assert reply in SYSTEM_PROMPT


def test_prompt_variables():
    assert set(ANSWER_PROMPT.input_variables) == {"context", "messages"}
    assert set(SMALL_TALK_PROMPT.input_variables) == {"messages"}
    assert set(REWRITE_PROMPT.input_variables) == {"history", "question"}


def test_answer_and_small_talk_rules_are_separate():
    # 답변 프롬프트에는 답변 규칙만, 일상 대화 프롬프트에는 일상 대화 규칙만 붙는다
    answer_text = ANSWER_PROMPT.format_messages(context="문서", messages=[])[0].content
    small_talk_text = SMALL_TALK_PROMPT.format_messages(messages=[])[0].content
    assert answer_text.startswith(SYSTEM_PROMPT + "\n\n" + ANSWER_RULES)
    assert answer_text.endswith("[검색 문서]\n문서")
    assert small_talk_text == SYSTEM_PROMPT + "\n\n" + SMALL_TALK_RULES


def test_crisis_replies():
    # 위기 대응 답은 CRI-01(109)과 CRI-02(112) 모두다. 섞인 글에서도 찾는다
    assert CRISIS_REPLIES == [PERSONA["replies"]["CRI-01"], PERSONA["replies"]["CRI-02"]]
    assert "109" in CRISIS_REPLIES[0]
    assert contains_crisis_reply(CRISIS_REPLIES[1] + "\n\n그 부탁은 들어 드릴 수 없어요.")
    assert not contains_crisis_reply("그 부탁은 들어 드릴 수 없어요.")
