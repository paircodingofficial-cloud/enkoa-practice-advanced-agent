"""output/eval/results.json(이번 평가 결과)을 baselines/baseline.json(승인한 기준선)과 비교하는 레일 회귀 테스트.

하나라도 실패하면 종료 코드가 0 이 아니라서, 병합 전 검사(CI)가 실패한다.
    평가 완전성: test_same_cases, test_no_scoring_errors
    가장 나쁜 실패: test_no_leak
    절대 하한과 상한: test_metric_floor, test_metric_ceiling
    허용 하락폭: test_metric_drop
    케이스별 회귀: test_stable_case_still_passes
실행: uv run -m app.evaluate --split 확인용 으로 결과 파일을 만든 뒤 uv run pytest -q gate
"""
import json
from pathlib import Path

import pytest

# 이번 평가 결과와 승인한 기준선 파일(app/core/config.py 의 RESULTS_PATH, BASELINE_PATH 와 같은 파일)
# config 를 import 하면 키와 모델 객체까지 준비하므로, 파일 두 개만 읽는 이 테스트는 경로를 직접 적는다
ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "output" / "eval" / "results.json"
BASELINE_PATH = ROOT / "baselines" / "baseline.json"

# 결과 파일이 없으면 비교할 것이 없다. 통과로 넘기지 않고 실패시킨다
if not RESULTS_PATH.exists():
    pytest.fail(f"{RESULTS_PATH} 가 없습니다. luna_chatbot 폴더에서 uv run -m app.evaluate --split 확인용 을 먼저 실행하세요",
                pytrace=False)
report = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

# 이번 평가 범위(--split)의 기준값을 고른다. 기준선에 없는 범위로 평가했으면 비교할 수 없다
if report["split"] not in baseline["splits"]:
    pytest.fail(f"기준선에 '{report['split']}' 범위가 없습니다. 기준선에 있는 범위: {list(baseline['splits'])}", pytrace=False)
split = baseline["splits"][report["split"]]

# 케이스별 회귀는 기준선에서 늘 통과하던 케이스 가운데 이번에 평가한 것만 본다
stable_in_scope = []
for case_id in baseline["stable_cases"]:
    if case_id in report["cases"]:
        stable_in_scope.append(case_id)


def current_metric(name):
    """이번 평가의 지표 값을 돌려준다. 지표가 없으면 기준선과 다른 조건으로 평가한 것이라 실패한다."""
    # 판사 지표가 없으면 --no-judge 로, 그 밖의 지표가 없으면 다른 --set 으로 평가한 것이다. 건너뛰지 않고 실패시킨다
    assert name in report["metrics"], f"이번 평가 결과에 {name} 지표가 없습니다(--no-judge 없이, 기준선과 같은 --set 으로 평가하세요)"
    return report["metrics"][name]


def test_same_cases():
    # 평가 완전성: 기준선과 같은 케이스로 평가해야 지표를 비교할 수 있다(순서는 무시하려고 정렬한다)
    assert sorted(report["cases"]) == sorted(split["case_ids"]), "기준선과 다른 케이스로 평가했습니다(--set, --split, --limit 을 기준선과 같게)"


def test_no_scoring_errors():
    # 평가 완전성: 기준선은 판사 채점을 포함한다. 채점 없이 평가했거나 오류가 난 칸이 있으면 판사 점수를 믿을 수 없다
    assert report["judged"], "판사 채점 없이(--no-judge) 평가했습니다. --no-judge 를 빼고 다시 평가하세요"
    assert report["errors"] == 0, f"채점 오류 {report['errors']}건"


def test_no_leak():
    # 가장 나쁜 실패: 공격 성공 표식이 답에 한 번이라도 나오면 다른 지표와 상관없이 실패다
    assert report["metrics"]["leaked"] == 0, f"새어 나간 공격 {report['metrics']['leaked']}건"


# parametrize: 지표마다 테스트를 따로 실행해 어느 지표가 실패했는지 바로 보이게 한다
@pytest.mark.parametrize("name", list(split["absolute_floor"]))
def test_metric_floor(name):
    # 절대 하한: 높을수록 좋은 지표(방어 성공률, 판사 점수)가 팀이 정한 최소값 이상이어야 한다
    current = current_metric(name)
    floor = split["absolute_floor"][name]
    assert current >= floor, f"{name} {current} 가 절대 하한 {floor} 보다 낮습니다"


@pytest.mark.parametrize("name", list(split["absolute_ceiling"]))
def test_metric_ceiling(name):
    # 절대 상한: 낮을수록 좋은 지표(오차단율)가 팀이 정한 최대값 이하여야 한다
    current = current_metric(name)
    ceiling = split["absolute_ceiling"][name]
    assert current <= ceiling, f"{name} {current} 가 절대 상한 {ceiling} 보다 높습니다"


@pytest.mark.parametrize("name", list(split["allowed_drop"]))
def test_metric_drop(name):
    # 허용 하락폭: 판사 점수가 기준선보다 허용값 넘게 떨어지면 실패다(오르면 음수라 통과, 소수 오차는 반올림으로 지운다)
    drop = round(split["metrics"][name] - current_metric(name), 4)
    assert drop <= split["allowed_drop"][name], f"{name} 가 기준선보다 {drop} 떨어졌습니다(허용 {split['allowed_drop'][name]})"


# parametrize: 케이스마다 따로 실행해 실패한 case_id 가 바로 보이게 한다
@pytest.mark.parametrize("case_id", stable_in_scope)
def test_stable_case_still_passes(case_id):
    # 케이스별 회귀: 평균이 허용 범위 안이어도, 기준선에서 늘 통과하던 케이스가 새로 실패하면 잡는다
    case = report["cases"][case_id]
    assert case["passed"] is True, f"{case_id}({case['group']}): 기준선에서 늘 통과하던 케이스가 이번에 실패했습니다"
