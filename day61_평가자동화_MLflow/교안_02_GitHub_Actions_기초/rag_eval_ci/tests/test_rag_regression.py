"""reports/results.json 을 baselines/baseline.json 과 비교하는 RAG 회귀 테스트입니다."""
import json
from pathlib import Path

import pytest

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
    # 순서와 상관없이 비교하려고 정렬합니다. 사례가 빠지거나 바뀌었으면 실패합니다.
    assert sorted(report["cases"].keys()) == sorted(split["case_ids"]), "기준선과 다른 사례로 평가했습니다"


def test_no_scoring_errors():
    assert report["errors"] == 0, f"채점 오류 {report['errors']}건"


@pytest.mark.parametrize("name", JUDGED_SCORERS)
def test_metric_floor(name):
    current = report["metrics"][name]
    assert current >= split["absolute_floor"][name], f"{name} {current} 가 절대 하한 {split['absolute_floor'][name]} 보다 낮습니다"


@pytest.mark.parametrize("name", JUDGED_SCORERS)
def test_metric_drop(name):
    drop = round(split["metrics"][name] - report["metrics"][name], 4)
    assert drop <= split["allowed_drop"][name], f"{name} 가 기준선보다 {drop} 떨어졌습니다(허용 {split['allowed_drop'][name]})"


@pytest.mark.parametrize("case_id", stable_in_scope)
def test_stable_case_still_passes(case_id):
    case = report["cases"][case_id]
    for name in JUDGED_SCORERS:
        assert case[name] is True, f"{case_id}: 기준선에서 늘 통과하던 질문이 {name} 에서 실패했습니다"
