"""실행 층: 터미널에서 루나와 여러 턴 대화하는 CLI.

실행: uv run -m app.main --fan F0001              (새 대화)
      uv run -m app.main --fan F0001 --thread ID  (앞 대화 이어 하기)
턴마다 루나의 답과 레일 기록 한 줄(막은 흐름, 경로, 뺀 문서)을 찍는다. exit 를 입력하면 끝난다.
"""
import argparse
import asyncio
from uuid import uuid4

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import CHECKPOINT_PATH
from app.graph.builder import build_app
from app.graph.chat import build_chat_context, send_message, summarize_turn


# [보조 함수] 레일 기록 한 줄
def trace_line(summary: dict) -> str:
    """턴 요약에서 경로, 막은 흐름과 규칙, 검색 문서, 뺀 문서를 " | " 로 이은 한 줄 글로 돌려준다."""
    # 경로는 늘 넣고, 나머지는 그 일이 있었던 턴에만 넣는다(막음, 가림, 검색, 검색 레일이 뺀 문서)
    parts = ["경로 " + summary["route"]]
    if summary["blocked_by"] != "":
        parts.append(f"막음 {summary['blocked_by']} ({summary['rule_id']})")
    if summary["output_status"] == "modified":
        parts.append("출력 가림")
    if len(summary["retrieved_ids"]) > 0:
        parts.append("검색 " + ", ".join(summary["retrieved_ids"]))
    if len(summary["removed_doc_ids"]) > 0:
        parts.append("뺀 문서 " + ", ".join(summary["removed_doc_ids"]))
    return " | ".join(parts)


# [보조 함수] 명령줄 인자
def parse_args() -> argparse.Namespace:
    """--fan(로그인한 팬 id)과 --thread(이어 할 대화 ID) 인자를 읽어 돌려준다."""
    parser = argparse.ArgumentParser(description="루나 레일 챗봇 CLI")
    parser.add_argument("--fan", default=None, help="로그인한 팬 id(예: F0001). 없으면 로그인하지 않은 팬")
    parser.add_argument("--thread", default=None, help="이어 할 대화 ID. 없으면 새 대화")
    return parser.parse_args()


# [실행 함수] 터미널 대화 반복
async def chat(fan_id: str | None, thread_id: str) -> None:
    """한 대화 ID 로 팬 메시지를 받아 답을 찍는 일을 exit 를 입력할 때까지 되풀이한다(돌려주는 값 없음)."""
    context = build_chat_context(fan_id)

    # 대화 기록을 SQLite 파일에 저장해, 프로그램을 껐다 켜도 같은 대화 ID 로 이어 할 수 있게 한다
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(CHECKPOINT_PATH) as connection:
        app = build_app(AsyncSqliteSaver(connection))

        # 이어 하는 대화면 저장된 메시지 수를 알려 준다
        saved = await app.aget_state({"configurable": {"thread_id": thread_id}})
        if "messages" in saved.values:
            print(f"저장된 메시지 {len(saved.values['messages'])}개에 이어서 대화합니다.")

        while True:
            text = input("\n팬> ").strip()

            # exit 면 끝내고, 빈 줄이면 다시 묻는다
            if text == "exit":
                break
            if text == "":
                continue

            # 한 턴을 보내고 답과 레일 기록 한 줄을 찍는다
            state = await send_message(app, thread_id, text, context)
            summary = summarize_turn(state)
            print("루나>", summary["answer"])
            print("  [레일]", trace_line(summary))


if __name__ == "__main__":
    args = parse_args()

    # 대화 ID 는 대화마다 새로 만든다. 같은 ID 를 다시 주면 앞 대화에 이어진다
    thread = args.thread
    if thread is None:
        thread = str(uuid4())
    print("로그인한 팬:", args.fan, "/ 대화 ID:", thread)
    print("끝내려면 exit 를 입력하세요.")
    asyncio.run(chat(args.fan, thread))

    # 같은 팬, 같은 대화 ID 로 다시 실행하면 이어진다
    resume_command = f"uv run -m app.main --thread {thread}"
    if args.fan is not None:
        resume_command = f"uv run -m app.main --fan {args.fan} --thread {thread}"
    print("\n이어서 하려면:", resume_command)
