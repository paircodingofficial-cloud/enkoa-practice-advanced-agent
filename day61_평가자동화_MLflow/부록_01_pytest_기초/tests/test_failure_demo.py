"""실패한 테스트의 출력을 읽어 보려고 일부러 틀린 기대값을 적은 파일입니다.

실행 방법(부록_01_pytest_기초 폴더에서): uv run pytest tests/test_failure_demo.py
"""
from citation_check import normalize


def test_keeps_line_break():
    # 일부러 틀린 기대값: normalize 는 줄바꿈을 공백으로 바꾸므로 이 테스트는 실패합니다.
    result = normalize("일반 도서를\n14일 동안")
    assert result == "일반 도서를\n14일 동안", "normalize 결과가 원래 문장과 다릅니다"
