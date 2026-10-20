"""가드 층: Jev 로 정책 위반 확률, 걸린 규칙 id, 답변이 근거로 뒷받침될 확률을 판정한다(Jev API 를 부른다).

레일 액션(guards/actions.py)과 라우터(guards/router.py)가 여기의 Jev 분류기(jev)를 함께 쓴다.

정책 글과 규칙 후보는 부르는 쪽이 인자로 넘긴다(core/prompts.py 의 정책 글 상수와 persona.yaml 의 규칙 후보 표).
판정할 상태(state)도 부르는 쪽이 만든다. 예: {"user_message": 팬 메시지, "previous_user_messages": 앞선 팬 메시지 목록}
이 파일에는 판정 질문 문장(규칙 고르기 지시, '해당 없음', 사실 대조 지시)만 둔다.
"""
import warnings

from langchain_typesafe import Choice, Noul, TypeSafeClassifier

from app.core.config import settings

warnings.filterwarnings("ignore", message=".*TypeSafeClassifier.*beta")  # 베타 안내 경고만 끈다

# Jev 분류기. 질문(Noul 확률, Choice 고르기)과 상태를 주면 판정 결과를 돌려준다. 만들 때는 API 를 부르지 않는다
jev = TypeSafeClassifier(model=settings.typesafe_model)

# 위반 규칙 후보에 함께 넣는 '해당 없음' 이름
NO_RULE = "none"

# 사실 대조 질문: 모른다고 안내하는 문장은 사실이 아니므로 대조하지 않게 한다
FACTS_INSTRUCTION = (
    "봇 답변이 단정한 사실(날짜, 시각, 가격, 기한, 조건, 혜택)이 모두 검색 문서에 적혀 있나요? "
    "문서에 없는 사실을 덧붙였으면 아니요입니다. 단정한 사실이 하나도 없으면 예입니다. "
    "'만들었어요', '바꿨어요'처럼 도구가 한 일을 알리는 문장은 문서(도구 결과)에 그 일이 적혀 있으면 뒷받침된 것입니다. "
    "'확인할 수 없습니다', '아직 공지되지 않았어요'처럼 모른다고 안내하는 문장은 사실이 아니므로 대조하지 않습니다. "
    "인사, 공감, 메뉴 경로 안내는 대조하지 않습니다."
)


# [판정 함수] 위반 확률과 규칙 id 묻기
async def jev_policy_judgement(state: dict, policy: str, rules: dict) -> dict:
    """판정 값 {"probability": 상태가 정책을 어길 확률(0~1), "rule_id": 가장 가까운 규칙 id(없으면 빈 문자열)} 을 돌려준다."""
    # 위반 확률(Noul)과 규칙 고르기(Choice)를 한 번의 호출로 함께 묻는다
    questions = {"violation": Noul(instructions=policy)}

    # 규칙 후보를 받았을 때만 규칙 고르기 질문을 더한다
    if rules:
        # 규칙 후보(id: 설명)에 '해당 없음'을 더해, 어느 규칙에도 맞지 않으면 그것을 고르게 한다
        criteria = dict(rules)
        criteria[NO_RULE] = "위 항목 어느 것에도 해당하지 않는다"
        questions["rule"] = Choice(instructions="상태가 아래 정책 항목 가운데 어느 항목에 가장 잘 해당하는지 하나만 고르세요.", criteria=criteria)
    decision = await jev.ainvoke({"state": state, "questions": questions})

    # 규칙 후보를 주지 않았으면 규칙 id 는 빈 문자열이다
    rule_id = ""

    # 규칙 후보를 줬으면 Jev 가 고른 규칙 id 를 읽는다
    if rules:
        rule_id = decision.choices["rule"].choice

    # '해당 없음'을 골랐으면 규칙 id 를 비운다(부르는 액션이 IN-?, OUT-? 로 바꾼다)
    if rule_id == NO_RULE:
        rule_id = ""
    return {"probability": decision.nouls["violation"].noul, "rule_id": rule_id}


# [판정 함수] 사실 대조
async def jev_facts_probability(answer: str, documents: str) -> float:
    """루나 답이 근거 글(documents)로 뒷받침될 확률(0~1)을 돌려준다. 근거 글이 없으면 1.0 이다."""
    # 문서를 넘기지 않으면 NeMo 가 빈 줄('\n')이나 '$relevant_chunks' 글자를 그대로 넘긴다. 문서가 없는 것과 같게 본다
    # 대조할 문서가 없으면 막을 근거도 없으므로 뒷받침된 것으로 본다(API 를 부르지 않는다)
    if documents.strip() in ("", "$relevant_chunks"):
        return 1.0

    # 근거가 있으면 답과 근거를 함께 보여 뒷받침될 확률을 묻는다
    decision = await jev.ainvoke({
        "state": {"bot_answer": answer, "documents": documents},
        "questions": {"supported": Noul(instructions=FACTS_INSTRUCTION)},
    })
    return decision.nouls["supported"].noul


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.guards.judges
    # 아래 확인은 API 를 부르지 않는다. 실제 판정은 Jev 를 호출하므로 레일(app.guards.rails)로 확인한다
    import asyncio

    print("Jev 모델:", settings.typesafe_model)
    print("'해당 없음' 이름:", NO_RULE)
    print("문서 없을 때 사실 대조:", asyncio.run(jev_facts_probability("11월 8일이에요.", "")))
    print("NeMo 가 빈 문서 자리를 그대로 넘길 때 사실 대조:", asyncio.run(jev_facts_probability("11월 8일이에요.", "$relevant_chunks")))
