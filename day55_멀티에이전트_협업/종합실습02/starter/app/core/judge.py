"""판정 층: Jev 분류기와 확률, 점수로 받는 판정 질문(보충 조사 필요 여부, 초안 통과)을 정한다."""
from langchain_typesafe import Noul, Score, TypeSafeClassifier

from app.core.config import TYPESAFE_MODEL

# Jev 분류기. 질문(Noul, Score)을 주면 확률(0~1)이나 점수(0~3)로 답한다. 키는 TYPESAFE_API_KEY.
classifier = TypeSafeClassifier(model=TYPESAFE_MODEL)

# Noul: 예/아니오 질문. 결과는 "예일 확률"로 나온다.
GAP_QUESTION = Noul(
    instructions=(
        "이 브리프의 gaps 에 블로그 글과 쇼츠 대본을 쓰기 전에 반드시 추가 조사해야 하는 항목이 있는가? "
        "글의 핵심 주장을 뒷받침할 사실이나 출처가 빠져 있으면 예, 있으면 좋은 정도의 보충이면 아니오."
    ),
)

# Score: 기준(criteria)을 0~3점으로 매기는 질문. contradiction 만 확률 질문이다.
DRAFT_QUESTIONS = {
    "source_fidelity": Score(
        instructions=(
            "초안의 수치와 주장이 함께 제공된 조사 결과(findings)와 분석 보고서로 뒷받침되는가? "
            "분석 보고서는 사내 데이터라 그 자체로 근거로 인정한다."
        ),
        criteria=[
            "출처 없는 주장이나 지어낸 수치가 많다.",
            "일부 주장만 출처가 있다.",
            "대부분 출처가 있고 본문에 표기했다.",
            "모든 핵심 주장에 출처가 있고 본문에 정확히 표기했다.",
        ],
    ),
    "reader_value": Score(
        instructions="독자가 이 블로그 글과 쇼츠 대본에서 바로 써먹을 정보를 얻는가?",
        criteria=[
            "일반론뿐이라 얻을 것이 없다.",
            "쓸 만한 내용이 조금 있다.",
            "구체적 사례나 방법이 있어 도움이 된다.",
            "다른 콘텐츠에 없는 구체적 방법과 근거가 있어 매우 유용하다.",
        ],
    ),
    "contradiction": Noul(
        instructions="이 초안의 핵심 주장과 수치가 조사 결과나 분석 보고서와 어긋나는가?",
    ),
}


# [보조 함수] 보충 조사 판정: 브리프의 gaps 에 꼭 더 조사해야 할 항목이 있을 확률을 Jev 로 받는다.
async def check_gaps(brief: dict) -> float:
    """브리프의 gaps 에 글을 쓰기 전에 꼭 조사해야 할 항목이 있을 확률(0~1)을 돌려준다."""
    # state 는 판정할 자료, questions 는 이름을 붙인 질문 묶음이다.
    result = await classifier.ainvoke({"state": brief, "questions": {"gap": GAP_QUESTION}})
    # gap 질문에 대한 '예일 확률'만 꺼낸다. supervisor 가 0.5 를 기준으로 갈 곳을 정한다.
    return result.nouls["gap"].noul


# [보조 함수] 초안 판정: 출처 충실도, 독자 가치 점수와 자료와 어긋날 확률을 Jev 로 받는다.
async def judge_draft(draft: str, findings: dict, report: str) -> dict:
    """출처 충실도, 독자 가치 점수(0~3)와 자료와 어긋날 확률(0~1)을 담은 딕셔너리를 돌려준다."""
    result = await classifier.ainvoke(
        {"state": {"draft": draft, "findings": findings, "report": report}, "questions": DRAFT_QUESTIONS}
    )
    # 결과에서 점수와 확률만 꺼내 평범한 딕셔너리로 만든다. reviewer 가 이 값으로 통과를 정한다.
    return {
        "source_fidelity": result.scores["source_fidelity"].score,
        "reader_value": result.scores["reader_value"].score,
        "contradiction": result.nouls["contradiction"].noul,
    }
