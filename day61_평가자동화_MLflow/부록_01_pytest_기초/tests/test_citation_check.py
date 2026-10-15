"""citation_check.py 의 테스트입니다. test_ 로 시작하는 함수 하나가 테스트 하나입니다.

실행 방법(부록_01_pytest_기초 폴더에서): uv run pytest -v tests/test_citation_check.py
"""
import pytest

from citation_check import check_citation, normalize


# 1) assert 로 쓴 기본 테스트: normalize 가 뜻과 상관없는 표기 차이를 하나로 맞추는지 확인합니다.
#    assert 실행 결과 == 기대값: 왼쪽에 함수가 돌려준 값, 오른쪽에 정답으로 정한 값을 쓰는 것이 관례입니다.
#    실패하면 pytest 가 이 순서로 차이를 보여 줍니다(- 는 기대값, + 는 실행 결과).
def test_line_break_becomes_space():
    # 줄바꿈은 공백 하나가 됩니다.
    assert normalize("일반 도서를\n14일 동안") == "일반 도서를 14일 동안"


def test_many_spaces_become_one():
    assert normalize("1인   7권까지") == "1인 7권까지"


def test_middle_dot_shapes_are_unified():
    # 모양이 다른 가운뎃점(･, ∙)이 모두 "·" 하나로 바뀌어야 합니다.
    assert normalize("대출･반납∙연장") == "대출·반납·연장"


# 2) fixture: 인용 검사 테스트들이 함께 쓰는 원문 사전을 테스트마다 새로 만들어 넘깁니다.
@pytest.fixture
def source_texts():
    """근거 ID -> 원문 사전입니다. 줄바꿈이 섞인 원문으로 정규화까지 확인합니다."""
    return {
        "loan-basic": "회원은 일반 도서를 1인 7권까지\n14일 동안 빌릴 수 있습니다.",
        "reading-room": "열람실 좌석은 4시간 단위로 예약합니다.",
    }


# 3) parametrize: 입력만 바꿔 같은 확인을 네 번 합니다. 줄마다 따로 판정합니다.
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
    # 이번에 검색한 문서는 loan-basic 하나입니다.
    assert check_citation(citation, source_texts, ["loan-basic"]) == expected
