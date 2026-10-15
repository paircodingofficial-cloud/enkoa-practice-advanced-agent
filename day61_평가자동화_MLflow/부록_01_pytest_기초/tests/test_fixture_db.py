"""fixture 로 도서관 DB(library.db)에 연결해 테스트에 넘기고, 테스트가 끝나면 연결을 닫습니다.

실행 방법(부록_01_pytest_기초 폴더에서): uv run pytest -v -s tests/test_fixture_db.py
-s 는 fixture 안의 print 를 화면에 보여 주는 옵션입니다.
"""
import sqlite3

import pytest


# 1) 기본 범위(function): 테스트마다 연결을 새로 열어 넘기고, 테스트가 끝나면 닫습니다.
@pytest.fixture
def library_db():
    # 준비: 이 폴더의 library.db 에 연결합니다.
    conn = sqlite3.connect("library.db")
    print("\n[library_db] 연결 열기")

    # yield: 연결을 테스트에 넘기고, 테스트가 끝날 때까지 여기서 기다립니다.
    yield conn

    # 정리: 테스트가 통과하든 실패하든 실행됩니다.
    conn.close()
    print("\n[library_db] 연결 닫기")


def test_library_general_loan_days(library_db):
    row = library_db.execute("SELECT loan_days FROM loan_rules WHERE book_type = '일반 도서'").fetchone()
    assert row[0] == 14


def test_library_rule_count(library_db):
    assert library_db.execute("SELECT COUNT(*) FROM loan_rules").fetchone()[0] == 3


# 2) module 범위: 이 파일에서 연결을 한 번만 열고, 파일 안의 테스트가 그 연결을 나눠 씁니다.
#    한 테스트가 DB 를 고치면 다음 테스트도 고친 DB 를 보게 되므로, 읽기만 하는 테스트에 씁니다.
@pytest.fixture(scope="module")
def shared_db():
    conn = sqlite3.connect("library.db")
    print("\n[shared_db] 연결 열기")

    yield conn

    conn.close()
    print("\n[shared_db] 연결 닫기")


def test_shared_new_book_days(shared_db):
    row = shared_db.execute("SELECT loan_days FROM loan_rules WHERE book_type = '신간 코너 도서'").fetchone()
    assert row[0] == 7


def test_shared_new_book_max(shared_db):
    row = shared_db.execute("SELECT max_books FROM loan_rules WHERE book_type = '신간 코너 도서'").fetchone()
    assert row[0] == 3
