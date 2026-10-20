"""화면 층: 살아 있는 이벤트 루프가 루프에 묶인 객체를 여러 턴 다시 쓸 수 있는지, 화면이 가짜 객체로 도는지 확인한다."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st
from nemoguardrails.rails.llm.options import RailStatus
from streamlit.testing.v1 import AppTest

from app.core.policies import PERSONA
from app.ui.runner import BackgroundLoop
from tests.conftest import BLOCKED_REPLY, FakeLLM, FakeRails, make_context

CHAT_APP = Path(__file__).resolve().parents[1] / "app" / "ui" / "chat_app.py"


class LoopBoundClient:
    """처음 쓴 이벤트 루프에 묶이는 가짜 클라이언트(ChatOpenAI 의 HTTP 연결, NeMo 판정 객체 흉내)."""

    def __init__(self):
        self.loop = None

    async def call(self):
        running = asyncio.get_running_loop()
        if self.loop is None:
            self.loop = running
        # 처음 루프가 닫혔거나 다른 루프에서 부르면 실제 라이브러리처럼 오류를 낸다
        if self.loop is not running or self.loop.is_closed():
            raise RuntimeError("Event loop is closed")
        return "ok"


def test_asyncio_run_breaks_loop_bound_client():
    # 화면이 다시 실행될 때마다 asyncio.run 을 쓰면 두 번째 턴에서 깨진다(이 방법을 쓰지 않는 이유)
    client = LoopBoundClient()
    assert asyncio.run(client.call()) == "ok"
    with pytest.raises(RuntimeError):
        asyncio.run(client.call())


def test_background_loop_reuses_one_loop():
    # 살아 있는 루프 하나에 보내면 같은 객체를 여러 턴 다시 쓸 수 있다
    runner = BackgroundLoop()
    client = LoopBoundClient()
    for _ in range(3):
        assert runner.run(client.call()) == "ok"


def test_chat_app_with_fakes(tmp_path, monkeypatch, fake_jev):
    # 화면 스크립트를 실제로 실행하되, 판정 객체, 모델, Jev 는 가짜로 바꾼다
    fake_jev.routes = {"날씨": "out_of_scope"}

    def fake_build_chat_context(fan_id=None):
        return make_context(fan_id=fan_id)

    monkeypatch.setattr("app.graph.chat.build_chat_context", fake_build_chat_context)
    monkeypatch.setattr("app.graph.nodes.llm", FakeLLM(answer="11월 8일 오후 7시에 시작해요."))
    monkeypatch.setattr("app.core.config.CHECKPOINT_PATH", tmp_path / "chat.sqlite")
    st.cache_resource.clear()

    app = AppTest.from_file(str(CHAT_APP), default_timeout=60)
    app.run()
    assert not app.exception

    # 업무 밖 질문(정해 둔 답), 정상 질문(RAG), 공격(입력 레일 차단)을 차례로 보낸다
    for text in ["오늘 날씨 어때요?", "팬미팅 몇 시예요?", "공격 문장입니다"]:
        app.chat_input[0].set_value(text).run()
        assert not app.exception
    shown = []
    for block in app.markdown:
        shown.append(block.value)
    page = "\n".join(shown)
    assert PERSONA["replies"]["OOS-07"] in page
    # 레일 판정 기록에 라우터가 고른 경로가 보인다
    assert "업무 밖 질문(정해 둔 답)" in page
    assert "검색(RAG)" in page
    assert "11월 8일 오후 7시에 시작해요." in page
    assert BLOCKED_REPLY in page
    assert "IN-05" in page
    assert "Lumi Night</b> 2026.11.08 19:00 루미너스홀" in page


class CrisisRails(FakeRails):
    """입력을 늘 Llama Guard 자해 범주(LG-S11)로 막고 위기 안내로 답하는 가짜 판정 객체."""

    async def check_async(self, messages, rail_types):
        return SimpleNamespace(status=RailStatus.BLOCKED, rail="llama guard 3 input",
                               content=PERSONA["replies"]["CRI-01"] + " 막은 규칙: LG-S11")


def test_crisis_reply_shown_as_bubble(tmp_path, monkeypatch):
    # Llama Guard 가 자해 범주(LG-S11)로 막아 위기 안내로 답한 턴은 막힘 카드가 아니라 루나 말풍선으로 보인다
    def fake_build_chat_context(fan_id=None):
        return make_context(fan_id=fan_id, rails=CrisisRails())

    monkeypatch.setattr("app.graph.chat.build_chat_context", fake_build_chat_context)
    monkeypatch.setattr("app.core.config.CHECKPOINT_PATH", tmp_path / "chat.sqlite")
    st.cache_resource.clear()

    app = AppTest.from_file(str(CHAT_APP), default_timeout=60)
    app.run()
    app.chat_input[0].set_value("요즘 너무 지쳐요").run()
    assert not app.exception
    shown = []
    for block in app.markdown:
        shown.append(block.value)
    page = "\n".join(shown)
    assert "109" in page
    # 막힘 카드 제목이 아니라 말풍선으로 그렸다
    assert "요청을 처리하지 않았어요" not in page
