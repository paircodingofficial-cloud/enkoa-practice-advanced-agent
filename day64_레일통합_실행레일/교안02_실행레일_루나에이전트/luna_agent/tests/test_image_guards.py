"""이미지 가드레일 테스트: 모더레이션 기준값, 브랜드 검사 실패 시 그림을 blocked 폴더에 남기기, 워터마크."""
import sqlite3
from uuid import uuid4

import aiosqlite
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from PIL import Image

from app.graph import builder
from app.graph.chat import summarize_turn
from app.guards.image_guards import brand_check, moderate_image, stamp_watermark
from tests.conftest import make_fake_model, png_bytes, tool_step


async def test_sexual_uses_stricter_threshold(fake_image, tmp_path):
    """sexual 은 기준값 0.2 를 쓰고, 다른 범주는 0.5 를 쓴다."""
    path = tmp_path / "art.png"
    path.write_bytes(png_bytes())

    fake_image["moderation"]["sexual"] = 0.25
    blocked = await moderate_image(path)
    assert blocked["passed"] is False
    assert blocked["rule_id"] == "MOD-sexual"

    fake_image["moderation"]["sexual"] = 0.1
    fake_image["moderation"]["violence"] = 0.4
    assert (await moderate_image(path))["passed"] is True

    fake_image["moderation"]["violence"] = 0.5
    assert (await moderate_image(path))["rule_id"] == "MOD-violence"


async def test_brand_check_fail_answer(fake_image, tmp_path):
    """그림 속 글자 질문(BRD-03)에 yes 가 나오면 실패다."""
    path = tmp_path / "art.png"
    path.write_bytes(png_bytes())
    assert (await brand_check(path))["passed"] is True
    fake_image["brand_fail"] = "BRD-03"
    failed = await brand_check(path)
    assert failed["passed"] is False
    assert failed["rule_id"] == "BRD-03"


async def test_brand_fail_keeps_image_in_blocked_and_records_block(monkeypatch, fake_rails, fake_image, make_context, tmp_path):
    """생성 뒤 브랜드 검사가 실패하면 그림을 보여 주지 않고 blocked 폴더로 옮기며, 하루 횟수에 넣지 않는 차단으로 기록한다."""
    fake_image["brand_fail"] = "BRD-01"
    monkeypatch.setattr(builder, "llm", make_fake_model(
        tool_step("create_fanart", {"request": "가을 단풍길 루나"}, "c1"), AIMessage("보여 드리지 못했어요.")))
    connection = await aiosqlite.connect(str(tmp_path / "chat.sqlite"))
    app = builder.build_app(AsyncSqliteSaver(connection))
    context = make_context("F0003")
    result = await app.ainvoke({"messages": [HumanMessage("가을 단풍길 루나 그려 줘")]},
                               config={"configurable": {"thread_id": str(uuid4())}}, context=context)
    await connection.close()

    event = summarize_turn(result)["tool_events"][0]
    assert event["rail"] == "check_fanart_image"
    assert event["artifact"]["path"] is None
    assert event["artifact"]["remaining"] == 3
    assert list((tmp_path / "fanart").glob("*.png")) == []
    kept = list((tmp_path / "fanart" / "blocked").glob("*.png"))
    assert len(kept) == 1
    assert event["artifact"]["blocked_path"] == str(kept[0])
    db =sqlite3.connect(context.db_path)
    row = db.execute("SELECT status, block_reason FROM fanart_requests ORDER BY request_id DESC LIMIT 1").fetchone()
    db.close()
    assert row == ("차단", "BRD-01")


def test_watermark_changes_bottom_right_only(tmp_path):
    """워터마크는 그림 크기를 바꾸지 않고 오른쪽 아래만 바꾼다."""
    path = tmp_path / "art.png"
    Image.new("RGB", (512, 512), (200, 180, 230)).save(path)
    stamp_watermark(path)
    stamped = Image.open(path).convert("RGB")
    assert stamped.size == (512, 512)
    assert stamped.getpixel((10, 10)) == (200, 180, 230)
    assert stamped.getpixel((480, 490)) != (200, 180, 230)
