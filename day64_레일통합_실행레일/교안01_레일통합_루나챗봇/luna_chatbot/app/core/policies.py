"""정책 층: 정책 원본 문서(persona.yaml)를 읽고, 레일이 막은 규칙 id 로 팬에게 보낼 정해 둔 답을 찾는다.

규칙과 문장을 바꿀 때는 코드가 아니라 persona.yaml 을 고친다. 모델에게 보내는 글은 core/prompts.py 가 모은다.
"""
import yaml

from app.core.config import PERSONA_PATH

# 앱이 시작할 때 한 번만 읽는다. persona.yaml 을 고쳤으면 앱을 다시 실행한다
with open(PERSONA_PATH, encoding="utf-8") as persona_file:
    PERSONA = yaml.safe_load(persona_file)

# 위기 신호에 답하는 정해 둔 문장(CRI-01 109 안내, CRI-02 112 신고 안내). 입력 레일이 막은 메시지에도 빠지면 안 된다
CRISIS_REPLIES = [PERSONA["replies"]["CRI-01"], PERSONA["replies"]["CRI-02"]]


# [정책 조회] 막은 규칙에 맞는 안내 문장
def reply_for_rule(rule_id: str) -> str:
    """레일이 막은 규칙 id 에 맞는 팬 안내 문장을 돌려준다."""
    # 규칙 id -> 답 id 표(rule_replies), 답 id -> 문장 표(replies) 두 단계로 찾는다
    rule_replies = PERSONA["rule_replies"]

    # 표에 있는 규칙 id 는 그 답 id 를 쓴다
    if rule_id in rule_replies:
        reply_id = rule_replies[rule_id]

    # 표에 없는 규칙 id(LG-S1, IN-? 같은 값)는 머리글자의 기본 답(LG-default 등)을 쓴다
    else:
        reply_id = rule_replies[rule_id.split("-")[0] + "-default"]
    return PERSONA["replies"][reply_id]


# [정책 조회] 위기 대응 답이 들었나
def contains_crisis_reply(text: str) -> bool:
    """글에 위기 대응 답 문장 하나가 그대로 들어 있으면 True 를 돌려준다."""
    # 위기 안내와 거절 문장이 이어 붙은 답도 위기 안내로 본다(화면이 막힘 카드 대신 말풍선으로 그린다)
    for reply in CRISIS_REPLIES:
        # 위기 안내 문장 하나라도 들어 있으면 True 다
        if reply in text:
            return True

    # 하나도 없으면 위기 안내가 아니다
    return False


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.core.policies
    print("페르소나 정책 버전:", PERSONA["version"], "/ 관리:", PERSONA["owner"])
    print("입력 규칙 수:", len(PERSONA["input_rules"]), "/ 출력 규칙 수:", len(PERSONA["output_rules"]))
    for sample_rule_id in ["PG2", "LG-S11", "LG-S1", "IN-05", "IN-?", "OUT-05", "OUT-08"]:
        print(sample_rule_id, "이 막았을 때:", reply_for_rule(sample_rule_id))
    print("위기 대응 답 수:", len(CRISIS_REPLIES), "/ 섞인 글에서 찾기:", contains_crisis_reply(CRISIS_REPLIES[1] + "\n\n그건 안 돼요."))
    print("공식 링크 도메인:", PERSONA["official_domains"])
