"""정책 층: 정책 원본 문서(persona.yaml, visual.yaml)를 한 번 읽어 두고, 막은 규칙 id 에 맞는 팬 안내 문장을 찾는다.

규칙과 문장을 바꿀 때는 코드가 아니라 YAML 을 고친다. 모델에 보내는 글은 core/prompts.py 가 이 dict 에서 꺼내 쓴다.
"""
import yaml

from app.core.config import PERSONA_PATH, VISUAL_PATH

# 모듈을 불러올 때 한 번만 읽는다. YAML 을 고쳤으면 앱을 다시 실행한다
with open(PERSONA_PATH, encoding="utf-8") as persona_file:
    PERSONA = yaml.safe_load(persona_file)   # 챗봇 말투, 판정 정책, 안내 문장(교안 01 과 같은 문서)
with open(VISUAL_PATH, encoding="utf-8") as visual_file:
    VISUAL = yaml.safe_load(visual_file)     # 팬아트 그림 정책(교안 02 만 쓴다)

# 판정 자체가 실패했을 때(판정 API 오류, 시간 초과) 남기는 규칙 id. persona.yaml rule_replies 가 안내 문장(REF-10)을 정한다
# 판정하지 못한 답이나 그림은 보내지 않는다(fail-closed). 실패를 통과로 보면 API 가 멈춘 동안 레일이 꺼진 것과 같다
RAIL_ERROR_RULE = "RAIL-ERROR"


# [정책 조회] 막은 규칙에 맞는 안내 문장
def reply_for_rule(rule_id: str) -> str:
    """레일이 막은 규칙 id 에 맞는 팬 안내 문장을 돌려준다."""
    rule_replies = PERSONA["rule_replies"]

    # 표에 없는 규칙 id(Jev 가 규칙을 못 고른 IN-? 같은 값)는 머리글자의 기본 답(IN-default 등)을 쓴다
    if rule_id in rule_replies:
        reply_id = rule_replies[rule_id]
    # 표에 없는 규칙 id: IN-? 는 IN-default, OUT-? 는 OUT-default 처럼 머리글자로 기본 답을 찾는다
    else:
        reply_id = rule_replies[rule_id.split("-")[0] + "-default"]
    return PERSONA["replies"][reply_id]


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.core.policies
    print("페르소나 정책 버전:", PERSONA["version"], "/ 관리:", PERSONA["owner"])
    print("입력 규칙 수:", len(PERSONA["input_rules"]), "/ 출력 규칙 수:", len(PERSONA["output_rules"]))
    print("IN-05 가 막았을 때:", reply_for_rule("IN-05"))
    print("PG2 가 막았을 때:", reply_for_rule("PG2"))
    print("규칙을 못 고른 IN-? 일 때:", reply_for_rule("IN-?"))
    print("OUT-08 이 막았을 때:", reply_for_rule("OUT-08"))
    print("판정이 실패했을 때:", reply_for_rule(RAIL_ERROR_RULE))
    print("공식 링크 도메인:", PERSONA["official_domains"])
    print("그림 정책 금지 주제 수:", len(VISUAL["forbidden_content"]), "/ 등급별 하루 한도:", VISUAL["generation"]["daily_limit"])
