"""실제 API 로 한 턴을 돌려 본다. RUN_LIVE=1 일 때만 실행한다(OpenAI, Jev 비용이 든다)."""
import pytest

from app.graph.builder import build_app
from app.graph.chat import build_chat_context, send_message, summarize_turn


@pytest.mark.live
async def test_live_one_turn():
    app = build_app()
    summary = summarize_turn(await send_message(app, "live-1", "팬클럽 LUMI 1기 연회비가 얼마예요?", build_chat_context()))
    assert summary["route"] == "rag"
    assert "33,000" in summary["answer"]
