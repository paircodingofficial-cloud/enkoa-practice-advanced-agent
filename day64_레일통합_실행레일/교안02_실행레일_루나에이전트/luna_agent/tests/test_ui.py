"""화면 테스트: Streamlit AppTest 로 채팅 화면을 가짜 모델과 가짜 레일로 돌려 카드와 승인 흐름을 확인한다."""
import sqlite3

import pytest
import streamlit as st
from langchain_core.messages import AIMessage
from streamlit.testing.v1 import AppTest

from app.core import config
from app.graph import builder
from tests.conftest import make_fake_model, tool_step

APP_FILE = "app/ui/chat_app.py"


@pytest.fixture
def ui(monkeypatch, tmp_path, fake_rails, db_copy):
    """체크포인터와 DB 를 임시 파일로 바꾼 화면 하나를 만드는 함수."""
    # AppTest 는 화면 파일을 새로 실행하므로, 그 파일이 import 하는 config 모듈 값을 바꾼다
    monkeypatch.setattr(config, "CHECKPOINT_PATH", tmp_path / "chat.sqlite")
    monkeypatch.setattr(config, "DB_PATH", db_copy)

    def build(*steps):
        monkeypatch.setattr(builder, "llm", make_fake_model(*steps))
        # 앞 테스트가 만든 에이전트(가짜 모델)를 다시 쓰지 않게 캐시를 비운다
        st.cache_resource.clear()
        app_test = AppTest.from_file(APP_FILE, default_timeout=60)
        app_test.run()
        return app_test

    return build


def markdown_text(app_test) -> str:
    """화면의 마크다운 조각을 한 글로 잇는다."""
    parts = []
    for block in app_test.markdown:
        parts.append(block.value)
    return "\n".join(parts)


def test_ticket_card_and_tool_chip(ui):
    """티켓 조회 턴에서 도구 표시, 티켓 카드, 루나 답이 그려진다."""
    app_test = ui(tool_step("get_my_tickets", {}, "c1"), AIMessage("좌석은 1층 B구역 7열 12번이에요."))
    app_test.chat_input[0].set_value("내 티켓 좌석 알려 줘").run()
    text = markdown_text(app_test)
    assert len(app_test.exception) == 0
    assert "get_my_tickets" in text
    assert "1층 B구역 7열 12번" in text
    assert "luna-card" in text


def test_empty_ticket_list_turn(ui):
    """티켓이 없는 팬(F0002)이 내 티켓을 물어도 화면이 깨지지 않고 루나 답이 그려진다."""
    app_test = ui(tool_step("get_my_tickets", {}, "c1"), AIMessage("예매한 티켓이 아직 없어요."))
    app_test.sidebar.selectbox[0].select("F0002").run()
    app_test.chat_input[0].set_value("내 티켓 보여 줘").run()
    assert len(app_test.exception) == 0
    assert "예매한 티켓이 아직 없어요" in markdown_text(app_test)


def test_approval_card_resumes_cancel(ui, db_copy):
    """취소가 승인을 기다리면 승인 카드가 뜨고, 승인을 누르면 멈춘 실행이 이어져 DB 가 바뀐다."""
    app_test = ui(tool_step("cancel_ticket", {"ticket_id": "T00097"}, "c1"), AIMessage("취소했어요. 88,000원을 돌려드려요."))
    app_test.sidebar.selectbox[0].select("F0003").run()
    app_test.chat_input[0].set_value("부산 공연 티켓 T00097 취소해 주세요.").run()
    assert "상담원 승인이 필요해요" in markdown_text(app_test)

    approve_button = None
    for button in app_test.button:
        if button.label == "승인":
            approve_button = button
    approve_button.click().run()
    assert len(app_test.exception) == 0
    assert "88,000원을 돌려드려요" in markdown_text(app_test)
    connection = sqlite3.connect(db_copy)
    status = connection.execute("SELECT status FROM tickets WHERE ticket_id = 'T00097'").fetchone()[0]
    connection.close()
    assert status == "취소"
