"""reports/results.json 을 baselines/baseline.json 과 비교하는 루나 팬 대화 챗봇 회귀 테스트입니다."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT / "reports" / "results.json").read_text(encoding="utf-8"))
baseline = json.loads((ROOT / "baselines" / "baseline.json").read_text(encoding="utf-8"))
# 이번 평가 범위(smoke 또는 full)에 맞는 기준값을 고릅니다.
split = baseline["splits"][report["split"]]
GATE_NAMES = list(split["metrics"])

# 사례별 회귀는 기준선에서 늘 통과하던 사례 가운데 이번에 평가한 것만 봅니다.
stable_in_scope = []
for case_id in baseline["stable_cases"]:
    if case_id in report["cases"]:
        stable_in_scope.append(case_id)


def test_same_cases():
    # 1. 이번 평가의 사례 ID 목록이 기준선의 같은 범위(split["case_ids"])와 같은지 확인하세요. 순서는 따지지 않습니다.
    pytest.fail("이 테스트를 작성하세요")


def test_no_scoring_errors():
    # 2. 채점 오류 수(report["errors"])가 0인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("name", GATE_NAMES)
def test_metric_floor(name):
    # 3. 이번 지표(report["metrics"][name])가 절대 하한(split["min"][name]) 이상인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("name", GATE_NAMES)
def test_metric_drop(name):
    # 4. 기준선 지표(split["metrics"][name])에서 이번 지표를 뺀 하락폭을 소수 넷째 자리로 반올림하고,
    #    허용 하락폭(split["max_drop"][name]) 이하인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")


@pytest.mark.parametrize("case_id", stable_in_scope)
def test_stable_case_still_passes(case_id):
    # 5. 이 사례의 판정(report["cases"][case_id])이 GATE_NAMES 의 모든 채점 함수에서 True 인지 확인하세요.
    pytest.fail("이 테스트를 작성하세요")
