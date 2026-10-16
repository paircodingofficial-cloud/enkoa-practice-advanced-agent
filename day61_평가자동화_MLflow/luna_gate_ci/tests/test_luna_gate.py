"""reports/results.json(이번 평가 결과)을 baselines/baseline.json(승인한 기준선)과 비교하는 루나 팬 대화 챗봇 회귀 테스트입니다.
하나라도 실패하면 종료 코드 1이 되어 CI 검사가 실패합니다.
    평가 완전성: test_same_cases, test_no_scoring_errors
    절대 하한: test_metric_floor
    허용 하락폭: test_metric_drop
    사례별 회귀: test_stable_case_still_passes
"""
import json
from pathlib import Path

import pytest

# 이번 평가 결과(report)와 승인한 기준선(baseline)을 읽습니다.
ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / "reports" / "results.json").read_text(encoding="utf-8"))
baseline = json.loads((ROOT / "baselines" / "baseline.json").read_text(encoding="utf-8"))
# 이번 평가 범위(smoke 또는 full)의 기준값과, 판정할 채점 함수 이름 목록
split = baseline["splits"][report["split"]]
JUDGED_SCORERS = list(split["metrics"])

# 사례별 회귀는 늘 통과하던 사례 중 이번에 평가한 것만 봅니다.
stable_in_scope = []
for case_id in baseline["stable_cases"]:
    if case_id in report["cases"]:
        stable_in_scope.append(case_id)


def test_same_cases():
    # 평가 완전성: 기준선과 같은 사례로 평가했는지
    # 1. 이번 평가의 사례 ID 목록이 기준선의 같은 범위(split["case_ids"])와 같은지 확인하세요. 순서는 따지지 않습니다.
    pytest.fail("이 테스트를 작성하세요")


def test_no_scoring_errors():
    # 평가 완전성: 채점 오류가 없는지
    # 2. 채점 오류 수(report["errors"])가 0인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("name", JUDGED_SCORERS)
def test_metric_floor(name):
    # 절대 하한: 이번 지표가 최소 품질 이상인지
    # 3. 이번 지표(report["metrics"][name])가 절대 하한(split["absolute_floor"][name]) 이상인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("name", JUDGED_SCORERS)
def test_metric_drop(name):
    # 허용 하락폭: 기준선보다 허용값 넘게 떨어지지 않았는지
    # 4. 기준선 지표(split["metrics"][name])에서 이번 지표를 뺀 하락폭을 소수 넷째 자리로 반올림하고,
    #    허용 하락폭(split["allowed_drop"][name]) 이하인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("case_id", stable_in_scope)
def test_stable_case_still_passes(case_id):
    # 사례별 회귀: 늘 통과하던 사례가 이번에도 통과했는지
    # 5. 이 사례의 판정(report["cases"][case_id])이 JUDGED_SCORERS 의 모든 채점 함수에서 True 인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")
