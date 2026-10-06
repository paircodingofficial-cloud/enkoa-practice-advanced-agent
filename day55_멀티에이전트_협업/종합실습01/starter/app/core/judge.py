"""판단 층: Jev 에게 묻는 질문(근거가 충분한지, 보고서 점수)과 호출 함수.

슈퍼바이저는 지시문까지 써야 하므로 GPT 구조화 출력을 쓰고, Jev 는 근거가 충분할 확률만 돌려준다.
끝낼지 말지는 그 확률을 보고 코드(가드)가 정한다.
"""
import warnings

from langchain_typesafe import Noul, Score, TypeSafeClassifier

from app.core.config import JEV_MODEL

warnings.filterwarnings("ignore", message=".*TypeSafeClassifier.*beta")   # 베타 안내 경고만 끈다
# Jev 분류기. 질문(Noul 확률, Score 점수)과 상태를 주면 판정 결과를 돌려준다
jev = TypeSafeClassifier(model=JEV_MODEL)

# 근거 충분 질문: Noul 은 예일 확률(0~1)을 돌려준다. 몇 이상이면 보고서로 넘길지는 supervisor 가 정한다
# 조건을 번호로 적어 두어야 보고 한두 개만으로 예라고 하지 않는다
ENOUGH_QUESTION = {
    "enough": Noul(
        instructions=(
            "findings 만으로 하락 원인 보고서를 쓸 수 있나요? 다음이 모두 갖춰졌을 때만 예다. "
            "1) 유입 경로별로 감소를 나눈 수치가 있다. "
            "2) 크게 줄어든 경로마다 한 단계 더 나눈 수치(검색어 유형별, 영상 노출 클릭률 등)와 꺾인 날짜가 있고, 왜 줄었는지 데이터나 문서 근거가 있다. "
            "3) 사내 문서와 외부 사건을 각각 한 번 이상 확인했다. "
            "4) 늘어난 지표처럼 원인으로 오해하기 쉬운 가설을 수치로 확인해 배제했다."
        ),
    ),
}
# Score: criteria 네 문장 중 보고서에 맞는 것으로 0~3점을 매기는 질문(첫 문장이 0점). contradiction 만 확률 질문이다
REVIEW_QUESTIONS = {
    "source_fidelity": Score(
        instructions="보고서의 수치와 원인 주장이 함께 제공된 findings 로 뒷받침되는가? findings 에 없는 수치는 근거가 없는 것이다.",
        criteria=[
            "근거 없는 수치나 지어낸 주장이 많다.",
            "일부 주장만 findings 로 뒷받침된다.",
            "대부분 뒷받침되고 출처를 적었다.",
            "모든 핵심 수치와 원인이 findings 로 뒷받침되고 출처를 정확히 적었다.",
        ],
    ),
    "usefulness": Score(
        instructions="보고서가 하락 원인별 근거 수치, 원인이 아닌 것의 배제 근거, 우선순위가 있는 대응안을 갖췄는가?",
        criteria=[
            "원인이나 대응안이 일반론뿐이다.",
            "원인은 있으나 근거 수치나 대응안이 빈약하다.",
            "원인마다 근거 수치가 있고 대응안이 있다.",
            "원인, 배제한 가설, 우선순위 있는 대응안을 근거 수치와 함께 모두 갖췄다.",
        ],
    ),
    "contradiction": Noul(
        instructions="보고서의 핵심 수치나 주장이 findings 와 어긋나는가?",
    ),
}


# [보조 함수] Jev 판정: judge_enough 는 슈퍼바이저 가드가, judge_report 는 검수자가 쓴다
async def judge_enough(request: str, findings: list[dict]) -> float:
    """지금까지의 보고로 보고서를 쓸 만큼 근거가 충분할 확률(0~1)을 돌려준다."""
    # findings 는 all_reports 가 만든 워커 이름과 결과만 든 목록이다(지시문과 턴 번호는 판정에 필요 없다)
    state = {"request": request, "findings": findings}
    # 질문 이름("enough")으로 결과를 꺼내 확률(noul)만 돌려준다
    result = await jev.ainvoke({"state": state, "questions": ENOUGH_QUESTION})
    return result.nouls["enough"].noul


async def judge_report(report: str, findings: list[dict]) -> dict:
    """출처 충실도, 유용성 점수(0~3)와 보고가 findings 와 어긋날 확률(0~1)을 딕셔너리로 돌려준다."""
    # Jev 에는 보고서와 워커 이름, 결과만 든 findings 를 넘긴다
    state = {"report": report, "findings": findings}
    result = await jev.ainvoke({"state": state, "questions": REVIEW_QUESTIONS})
    # 결과에서 점수와 확률만 꺼내 평범한 딕셔너리로 만든다. reviewer 가 이 값으로 통과를 정한다
    return {
        "source_fidelity": result.scores["source_fidelity"].score,
        "usefulness": result.scores["usefulness"].score,
        "contradiction": result.nouls["contradiction"].noul,
    }
