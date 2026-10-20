"""가드 층: Jev 에게 정해 둔 후보 가운데 하나만 고르게 하는 판정 두 가지(경로 고르기, 막힌 메시지 속 위기 신호 고르기).

고르기만 하는 일이라 Jev 의 Choice 를 쓴다(고르고 글까지 써야 하면 GPT 를 쓴다).
후보와 질문 문장은 core/prompts.py 에 있다(위기 신호 설명은 persona.yaml 의 crisis_signals 표).
Jev 호출이 실패하면 경로는 검색(rag)으로, 위기 신호는 '없음'으로 본다. 두 판정 모두 막는 일이 아니라 고르는 일이라 턴을 멈추지 않는다. Jev 분류기(jev)는 입력, 출력 레일과 같은 것을 guards/judges.py 에서 가져온다.
"""
from langchain_typesafe import Choice

from app.core.prompts import CRISIS_INSTRUCTION, CRISIS_SIGNALS, NO_CRISIS, ROUTE_INSTRUCTION, ROUTES
from app.guards.judges import jev

# Jev 가 쓸 만한 경로를 돌려주지 않았을 때 가는 경로. 검색해서 답하고, 답은 출력 레일이 검사한다
FALLBACK_ROUTE = "rag"


# [판정 함수] 경로 고르기
async def choose_route(messages: list) -> str:
    """최근 대화 기록(마지막이 팬 메시지)을 보고 ROUTES 가운데 경로 이름 하나를 돌려준다."""
    # 앞 대화를 "팬: ...", "루나: ..." 줄로 묶는다. "거기 어떻게 가요?" 처럼 앞 턴을 가리키는 질문도 고를 수 있게 한다
    earlier_lines = []
    for message in messages[:-1]:
        # 팬 메시지는 "팬: ", 그 밖(루나 답)은 "루나: " 를 붙인다
        if message.type == "human":
            earlier_lines.append("팬: " + message.text)
        else:
            earlier_lines.append("루나: " + message.text)

    # Jev 에게 보여 줄 상태: 마지막 팬 메시지와 앞 대화 줄
    state = {"user_message": messages[-1].text, "earlier_conversation": earlier_lines}

    # Jev 호출이 실패해도(API 장애, 시간 초과) 턴을 멈추지 않고 검색 경로로 보낸다. 검색 경로의 답도 출력 레일이 검사한다
    try:
        decision = await jev.ainvoke({
            "state": state,
            "questions": {"route": Choice(instructions=ROUTE_INSTRUCTION, criteria=ROUTES)},
        })
    except Exception:
        return FALLBACK_ROUTE

    # 답이 없거나 후보 밖의 이름이면 검색 경로로 보낸다
    answer = decision.choices.get("route")
    if answer is None or answer.choice not in ROUTES:
        return FALLBACK_ROUTE

    # 후보 안의 이름이면 그 경로다
    return answer.choice


# [판정 함수] 막힌 메시지 속 위기 신호 고르기
async def pick_crisis_reply_id(text: str) -> str:
    """팬 메시지 하나에 위기 신호가 있으면 그 답 id(CRI-01, CRI-02)를, 없으면 빈 문자열을 돌려준다."""
    # 이미 막힌 메시지라 거절은 그대로 나간다. Jev 호출이 실패하면 위기 안내만 붙이지 않는다
    try:
        decision = await jev.ainvoke({
            "state": {"user_message": text},
            "questions": {"crisis": Choice(instructions=CRISIS_INSTRUCTION, criteria=CRISIS_SIGNALS)},
        })
    except Exception:
        return ""

    # 답이 없거나, 후보 밖이거나, '없음'을 골랐으면 위기 신호가 없다
    answer = decision.choices.get("crisis")
    if answer is None or answer.choice not in CRISIS_SIGNALS or answer.choice == NO_CRISIS:
        return ""

    # 위기 신호를 골랐으면 그 답 id(정해 둔 위기 안내 문장의 id)다
    return answer.choice


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.guards.router
    # 후보만 본다. 실제 고르기는 Jev 를 호출하므로 그래프(app.graph.chat)나 평가(--routes-only)로 확인한다
    print("경로 후보:", list(ROUTES), "/ 기본 경로:", FALLBACK_ROUTE)
    print("위기 신호 후보:", list(CRISIS_SIGNALS))
