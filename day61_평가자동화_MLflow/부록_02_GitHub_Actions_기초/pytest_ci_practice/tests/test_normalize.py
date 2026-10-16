"""normalize 의 첫 테스트입니다. test_ 로 시작하는 함수 세 개가 각각 테스트 하나입니다.

실행 방법(pytest_ci_practice 폴더에서): uv run pytest -v tests/test_normalize.py
"""

from citation_check import normalize


def test_line_break_becomes_space():
    # 줄바꿈은 공백 하나가 됩니다.
    assert normalize("일반 도서를\n14일 동안") == "일반 도서를 14일 동안"


def test_many_spaces_become_one():
    assert normalize("1인   7권까지") == "1인 7권까지"


def test_middle_dot_shapes_are_unified():
    # 모양이 다른 가운뎃점(･, ∙)이 모두 "·" 하나로 바뀌어야 합니다.
    assert normalize("대출･반납∙연장") == "대출·반납·연장"
