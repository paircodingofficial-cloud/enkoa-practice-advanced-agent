"""reports/results.json(이번 평가 결과)을 baselines/baseline.json(승인한 기준선)과 비교하는 루나 팬 대화 챗봇 회귀 테스트입니다.

네 규칙을 테스트 함수로 확인합니다. 하나라도 실패하면 pytest 종료 코드가 1이 되어 CI 검사가 실패합니다.
    평가 완전성: test_same_cases, test_no_scoring_errors
    절대 하한: test_metric_floor
    허용 하락폭: test_metric_drop
    사례별 회귀: test_stable_case_still_passes
"""
import json
from pathlib import Path

import pytest

# 테스트에 쓸 두 파일을 읽습니다. report 는 이번 평가 결과, baseline 은 승인한 기준선입니다.
ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / "reports" / "results.json").read_text(encoding="utf-8"))
baseline = json.loads((ROOT / "baselines" / "baseline.json").read_text(encoding="utf-8"))
# 이번 평가 범위(smoke 또는 full)에 맞는 기준값을 고릅니다.
split = baseline["splits"][report["split"]]
# 판정에 쓰는 채점 함수 이름 목록입니다. 기준선에 지표를 저장한 채점 함수 이름을 그대로 씁니다.
JUDGED_SCORERS = list(split["metrics"])

# 사례별 회귀는 기준선에서 늘 통과하던 사례 가운데 이번에 평가한 것만 봅니다.
stable_in_scope = []
for case_id in baseline["stable_cases"]:
    if case_id in report["cases"]:
        stable_in_scope.append(case_id)


def test_same_cases():
    # 평가 완전성 1: 기준선과 같은 사례들로 평가했는지 확인하는 테스트입니다.
    # 1. 이번 평가의 사례 ID 목록이 기준선의 같은 범위(split["case_ids"])와 같은지 확인하세요. 순서는 따지지 않습니다.
    pytest.fail("이 테스트를 작성하세요")


def test_no_scoring_errors():
    # 평가 완전성 2: 채점 중 오류가 난 칸이 없는지 확인하는 테스트입니다.
    # 2. 채점 오류 수(report["errors"])가 0인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("name", JUDGED_SCORERS)
def test_metric_floor(name):
    # 절대 하한: 이번 지표가 팀이 정한 최소 품질 이상인지 확인하는 테스트입니다.
    # 3. 이번 지표(report["metrics"][name])가 절대 하한(split["absolute_floor"][name]) 이상인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("name", JUDGED_SCORERS)
def test_metric_drop(name):
    # 허용 하락폭: 지표가 기준선보다 허용 하락폭을 넘게 떨어지지 않았는지 확인하는 테스트입니다.
    # 4. 기준선 지표(split["metrics"][name])에서 이번 지표를 뺀 하락폭을 소수 넷째 자리로 반올림하고,
    #    허용 하락폭(split["allowed_drop"][name]) 이하인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("case_id", stable_in_scope)
def test_stable_case_still_passes(case_id):
    # 사례별 회귀: 기준선에서 늘 통과하던 사례가 이번에도 통과했는지 확인하는 테스트입니다.
    # 5. 이 사례의 판정(report["cases"][case_id])이 JUDGED_SCORERS 의 모든 채점 함수에서 True 인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")
