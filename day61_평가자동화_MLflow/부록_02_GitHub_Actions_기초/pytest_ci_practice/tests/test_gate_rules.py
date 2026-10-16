"""gate_rules 의 테스트입니다. 부록 02 워크플로의 gate-rules 작업이 실행합니다.

실행 방법(pytest_ci_practice 폴더에서): uv run pytest -v tests/test_gate_rules.py
"""

import pytest

from gate_rules import drop_allowed, metric_drop, regressed_cases


def test_metric_drop_sign():
    # 떨어지면 양수, 오르면 음수입니다.
    assert metric_drop(0.875, 0.75) == 0.125
    assert metric_drop(0.75, 0.875) == -0.125


@pytest.mark.parametrize(
    "baseline_value, current_value, allowed_drop, expected",
    [
        (0.875, 0.8125, 0.1, True),  # 0.0625 하락: 허용 하락폭보다 작음
        (0.875, 0.8125, 0.0625, True),  # 허용 하락폭과 같게 떨어지면 통과
        (0.875, 0.75, 0.0625, False),  # 0.125 하락: 허용 하락폭보다 큼
        (0.75, 0.875, 0.0625, True),  # 오르면 하락폭이 음수라 통과
    ],
    ids=["small_drop", "equal_drop", "big_drop", "rise"],
)
def test_drop_allowed(baseline_value, current_value, allowed_drop, expected):
    assert drop_allowed(baseline_value, current_value, allowed_drop) == expected


@pytest.fixture
def report_cases():
    """이번 평가의 사례별 판정입니다. lib-02 는 citation_valid 에서, lib-03 은 correctness 에서 실패했습니다."""
    return {
        "lib-01": {"correctness": True, "citation_valid": True},
        "lib-02": {"correctness": True, "citation_valid": False},
        "lib-03": {"correctness": False, "citation_valid": True},
    }


def test_regressed_cases(report_cases):
    # lib-03 은 늘 통과하던 사례가 아니라 빠지고, lib-09 는 이번 평가에 없어 빠집니다.
    stable_cases = ["lib-01", "lib-02", "lib-09"]
    assert regressed_cases(stable_cases, report_cases, ["correctness", "citation_valid"]) == ["lib-02"]
