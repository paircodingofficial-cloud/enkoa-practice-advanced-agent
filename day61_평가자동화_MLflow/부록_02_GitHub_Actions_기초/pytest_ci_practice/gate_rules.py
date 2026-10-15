"""회귀 게이트의 판정 규칙입니다. 교안 02 테스트 파일의 assert 조건을 함수로 옮겼습니다.

테스트할 코드라 직접 실행하지 않습니다. 이 파일의 테스트는 tests/test_gate_rules.py 에 있습니다.
실행 방법(pytest_ci_practice 폴더에서): uv run pytest -v tests/test_gate_rules.py
"""


def metric_drop(baseline_value, current_value):
    """기준선보다 떨어진 크기를 소수 넷째 자리로 반올림해 돌려줍니다. 오르면 음수입니다."""
    return round(baseline_value - current_value, 4)


def drop_allowed(baseline_value, current_value, max_drop):
    """하락폭이 허용 하락폭 이하이면 True 를 돌려줍니다. 허용 하락폭과 같으면 통과입니다."""
    return metric_drop(baseline_value, current_value) <= max_drop


def regressed_cases(stable_cases, report_cases, names):
    """늘 통과하던 사례 가운데 이번 평가에서 채점 함수 하나라도 실패한 case_id 목록을 돌려줍니다."""
    failed = []
    for case_id in stable_cases:
        # 이번에 평가하지 않은 사례(smoke 밖)는 보지 않습니다.
        if case_id not in report_cases:
            continue
        for name in names:
            if report_cases[case_id][name] is not True:
                failed.append(case_id)
                break
    return failed
