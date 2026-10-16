"""check_citation 의 네 가지 결과를 parametrize 로 한 테스트 함수에서 확인합니다.

실행 방법(pytest_ci_practice 폴더에서): uv run pytest -v tests/test_check_citation.py
"""

import pytest

from citation_check import check_citation


@pytest.fixture
def source_texts():
    """테스트마다 새로 만들어 주는 원문 사전입니다(근거 ID -> 원문)."""
    return {
        "loan-basic": "회원은 일반 도서를 1인 7권까지\n14일 동안 빌릴 수 있습니다.",
        "reading-room": "열람실 좌석은 4시간 단위로 예약합니다.",
    }


@pytest.mark.parametrize(
    "evidence_id, quote, expected",
    [
        ("loan-basic", "1인 7권까지 14일 동안", "확인"),
        ("loan-weekend", "주말에는 3일 더", "없는 근거 ID"),
        ("reading-room", "4시간 단위", "검색하지 않은 문서"),
        ("loan-basic", "1인 7권까지 30일 동안", "원문에 없는 문구"),
    ],
    ids=["ok", "unknown_id", "not_searched", "changed_number"],
)
def test_check_citation(source_texts, evidence_id, quote, expected):
    citation = {"evidence_id": evidence_id, "quote": quote}
    # 검색한 문서는 loan-basic 하나입니다.
    assert check_citation(citation, source_texts, ["loan-basic"]) == expected
