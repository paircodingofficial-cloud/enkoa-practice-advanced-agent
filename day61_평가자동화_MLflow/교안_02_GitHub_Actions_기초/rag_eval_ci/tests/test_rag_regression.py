"""reports/results.json(이번 평가 결과)을 baselines/baseline.json(승인한 기준선)과 비교하는 RAG 회귀 테스트입니다.

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
    # 평가 완전성 1: 기준선과 같은 사례들로 평가했는지 확인합니다.
    # 사례가 빠지거나 다른 사례가 섞이면 지표를 기준선과 비교할 수 없으므로 실패합니다.
    # 순서와 상관없이 비교하려고 정렬합니다.
    assert sorted(report["cases"].keys()) == sorted(split["case_ids"]), "기준선과 다른 사례로 평가했습니다"


def test_no_scoring_errors():
    # 평가 완전성 2: 채점 중 오류가 난 칸이 없는지 확인합니다.
    # 오류가 난 칸은 판정이 비어 있어 지표를 믿을 수 없으므로 실패합니다.
    assert report["errors"] == 0, f"채점 오류 {report['errors']}건"


# parametrize: 채점 함수마다(correctness, citation_valid) 테스트를 하나씩 따로 실행합니다.
@pytest.mark.parametrize("name", JUDGED_SCORERS)
def test_metric_floor(name):
    # 절대 하한: 이번 지표가 팀이 정한 최소 품질(absolute_floor) 이상인지 확인합니다.
    current = report["metrics"][name]
    assert current >= split["absolute_floor"][name], f"{name} {current} 가 절대 하한 {split['absolute_floor'][name]} 보다 낮습니다"


@pytest.mark.parametrize("name", JUDGED_SCORERS)
def test_metric_drop(name):
    # 허용 하락폭: 기준선 지표에서 이번 지표를 뺀 하락폭이 allowed_drop 이하인지 확인합니다.
    # 지표가 오르면 하락폭이 음수라 통과합니다. 소수 계산 오차를 없애려고 넷째 자리에서 반올림합니다.
    drop = round(split["metrics"][name] - report["metrics"][name], 4)
    assert drop <= split["allowed_drop"][name], f"{name} 가 기준선보다 {drop} 떨어졌습니다(허용 {split['allowed_drop'][name]})"


# parametrize: 늘 통과한 사례마다 테스트를 따로 실행해, 실패하면 어느 case_id 인지 바로 보입니다.
@pytest.mark.parametrize("case_id", stable_in_scope)
def test_stable_case_still_passes(case_id):
    # 사례별 회귀: 기준선에서 늘 통과하던 사례가 이번에도 모든 채점 함수에서 통과했는지 확인합니다.
    # 평균 지표가 허용 범위 안이어도 특정 사례가 새로 실패하면 여기서 잡힙니다.
    case = report["cases"][case_id]
    for name in JUDGED_SCORERS:
        assert case[name] is True, f"{case_id}: 기준선에서 늘 통과하던 질문이 {name} 에서 실패했습니다"
