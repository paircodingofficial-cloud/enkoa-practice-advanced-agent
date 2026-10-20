"""실행 층: 터미널에서 로그인한 팬으로 루나 에이전트와 여러 턴 대화하는 CLI.

실행: uv run -m app.main --fan F0001              (새 대화)
      uv run -m app.main --fan S0001 --role staff (운영팀 계정. 역할은 DB 의 로그인 정보와 같아야 한다)
      uv run -m app.main --fan F0003 --thread ID  (앞 대화 이어 하기)
턴마다 도구 호출과 레일 판정을 찍고, 승인이 필요하면 묻는다. exit 를 입력하면 끝난다.
승인을 기다리다 끈 대화를 이어 하면 새 메시지를 받기 전에 그 승인부터 묻는다.
"""
import argparse
import asyncio
from uuid import uuid4

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.core.config import CHECKPOINT_PATH
from app.core.prompts import REJECT_MESSAGE
from app.core.schemas import AgentContext
from app.graph.builder import build_app
from app.graph.chat import pending_actions, resume_turn, send_message, summarize_turn
from app.tools.fan_db import get_fan

# 승인 질문에 '승인' 으로 볼 대답
APPROVE_WORDS = ["승인", "y", "yes", "예", "네"]


# [보조 함수] 턴 결과 출력
def print_turn(summary: dict) -> None:
    """이번 턴의 입력 레일, 도구 호출과 실행 레일 결과, 출력 레일, 팬아트 파일, 답을 출력한다."""
    # 입력 레일이 돈 턴만 그 판정을 찍는다
    if summary["input_verdict"]:
        verdict = summary["input_verdict"]
        print(f"  [입력 레일] {verdict['status']} {verdict['blocked_by']} {verdict['rule_id']}".rstrip())

    # 도구마다 이름, 인자, 결과. 막혔으면 막은 미들웨어와 규칙 id 를 붙인다
    for event in summary["tool_events"]:
        line = f"  [도구] {event['name']} {event['args']} -> {event['status']}"
        if event["rail"]:
            line += f" ({event['rail']} {event['rule_id']})".rstrip()
        print(line)
        # 팬아트가 만들어졌으면 파일 경로를 보여 준다
        if event["name"] == "create_fanart" and event["artifact"] is not None and event["artifact"].get("path"):
            print("  [팬아트]", event["artifact"]["path"], "/ 오늘 남은 횟수:", event["artifact"]["remaining"])

    # 출력 레일이 막은 답을 다시 썼으면 그 단계와, 다시 쓴 답의 출력 레일 판정을 찍는다
    if summary["retry_count"] > 0:
        print("  [답 다시 쓰기] 출력 레일이 막은 답을 도구 없이 한 번 다시 씀")
    if summary["output_verdict"]:
        verdict = summary["output_verdict"]
        print(f"  [출력 레일] {verdict['status']} {verdict['blocked_by']} {verdict['rule_id']}".rstrip())
    # 승인 대기면 답이 아직 없어 찍지 않는다
    if summary["answer"]:
        print("루나>", summary["answer"])


# [보조 함수] 승인 받기
def ask_decisions(pending: list) -> list:
    """승인을 기다리는 작업마다 사람에게 승인, 거절을 물어 결정 목록을 돌려준다(작업 순서와 같은 순서)."""
    decisions = []
    for action in pending:
        print("  [승인 필요]", action["description"])
        answer = input("  승인할까요? (승인/거절) ").strip().lower()
        # 승인으로 볼 대답이면 approve
        if answer in APPROVE_WORDS:
            decisions.append({"type": "approve"})
        # 그 밖의 대답은 모두 거절로 본다(잘못 누른 대답으로 실행되지 않게)
        else:
            # 거절 이유는 모델에게 도구 결과로 전달된다. 모델은 실행하지 않았다고 팬에게 알린다
            decisions.append({"type": "reject", "message": REJECT_MESSAGE})
    return decisions


# [보조 함수] 승인 대기 처리
async def approve_pending(app, thread_id: str, pending: list, context) -> None:
    """승인 대기 작업이 없어질 때까지 결정을 받아 같은 대화 ID 로 이어 가고 결과를 출력한다. 이어 간 실행이 또 멈추면 다시 묻는다."""
    # 결정 하나로 이어 간 실행이 다시 승인 도구를 고르면 또 멈추므로, 승인 대기가 없어질 때까지 되풀이한다
    while pending:
        decisions = ask_decisions(pending)
        result = await resume_turn(app, thread_id, decisions, context)
        summary = summarize_turn(result)
        print_turn(summary)
        pending = summary["pending"]


# [보조 함수] 명령줄 인자
def parse_args() -> argparse.Namespace:
    """--fan(로그인할 계정 id), --role(확인용 역할), --thread(이어 할 대화 ID) 인자를 읽어 돌려준다."""
    parser = argparse.ArgumentParser(description="루나 에이전트 여러 턴 대화")
    parser.add_argument("--fan", default="F0001", help="로그인할 계정 id(F0001~F0200, S0001~S0005)")
    parser.add_argument("--role", choices=["fan", "staff"], default=None, help="확인용. 로그인 정보(DB)의 역할과 같아야 한다")
    parser.add_argument("--thread", default=None, help="이어 할 대화 ID. 없으면 새 대화")
    return parser.parse_args()


# [보조 함수] 대화 되풀이
async def chat(context: AgentContext, thread_id: str) -> None:
    """한 대화 ID 로 팬 메시지를 받아 에이전트를 돌리고, 승인 대기면 승인을 받아 이어 가는 일을 exit 까지 되풀이한다."""
    # 대화 기록과 승인 대기 실행을 SQLite 파일에 저장해, 프로그램을 껐다 켜도 같은 대화 ID 로 이어 할 수 있게 한다
    # async with: 오류나 Ctrl+C 로 빠져나가도 연결을 닫는다
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(CHECKPOINT_PATH) as connection:
        app = build_app(AsyncSqliteSaver(connection))

        # 이어 하는 대화면 저장된 메시지 수를 알려 준다
        saved = await app.aget_state({"configurable": {"thread_id": thread_id}})
        # 새 대화면 저장된 값이 비어 있어 건너뛴다
        if "messages" in saved.values:
            print(f"저장된 메시지 {len(saved.values['messages'])}개에 이어서 대화합니다.")

        # 승인을 기다리다 멈춘 대화면 새 메시지보다 승인을 먼저 받는다
        # 멈춘 대화에 새 메시지를 보내면 승인 대기가 버려지고, 결과 없는 도구 호출이 기록에 남아 실제 모델이 400 오류를 낸다
        await approve_pending(app, thread_id, pending_actions({"__interrupt__": saved.interrupts}), context)

        while True:
            text = input("\n팬> ").strip()
            # exit: 대화를 끝낸다. 빈 줄: 그래프를 부르지 않고 다시 묻는다
            if text == "exit":
                break
            if text == "":
                continue
            result = await send_message(app, thread_id, text, context)
            summary = summarize_turn(result)
            print_turn(summary)

            # 승인 대기면 결정을 받아 같은 대화 ID 로 이어 간다
            await approve_pending(app, thread_id, summary["pending"], context)


if __name__ == "__main__":
    # 실행: uv run -m app.main --fan F0001 (모델과 Jev 를 부르므로 비용이 든다)
    args = parse_args()

    # 역할은 DB 의 로그인 정보로 정한다. 명령줄에 다른 역할을 적어도 권한이 바뀌지 않는다
    fan = get_fan(args.fan)
    # 없는 계정이나, 명령줄 역할이 DB 역할과 다르면 시작하지 않는다
    if fan is None:
        raise SystemExit(f"없는 계정입니다: {args.fan}")
    if args.role is not None and args.role != fan["role"]:
        raise SystemExit(f"{args.fan} 의 역할은 {fan['role']} 입니다. 역할은 로그인 정보로만 정합니다.")

    # 대화 ID 는 대화마다 새로 만든다. 같은 ID 를 다시 주면 앞 대화에 이어진다
    thread = args.thread
    if thread is None:
        thread = str(uuid4())
    print(f"로그인: {fan['fan_id']}({fan['role']}) / 대화 ID: {thread}")
    print("끝내려면 exit 를 입력하세요.")
    asyncio.run(chat(AgentContext(fan_id=fan["fan_id"], role=fan["role"]), thread))
    print("\n이어서 하려면:", f"uv run -m app.main --fan {fan['fan_id']} --thread {thread}")
