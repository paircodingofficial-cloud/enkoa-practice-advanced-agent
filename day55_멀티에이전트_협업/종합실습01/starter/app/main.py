"""실행 층: uv run python -m app.main "요청" 으로 팀을 실행하는 CLI."""
import argparse
import asyncio
import json
from datetime import datetime

from langchain_core.messages import messages_to_dict
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agents.workers import create_workers
from app.core.config import OUTPUT_ROOT
from app.graph.builder import build_graph
from app.tools.mcp_servers import mcp_connections


async def main():
    """요청을 실행하고 산출물 폴더에 messages.json 을 저장한다(반환값 없음)."""
    # 명령줄 인자: 요청 문장 하나
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    args = parser.parse_args()

    # 실행할 때마다 시각 이름의 산출물 폴더를 새로 만든다. 차트, 보고서, 대화 기록이 모두 여기 모인다
    run_dir = OUTPUT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True)
    print("산출물 폴더:", run_dir)
    # 모델에게는 한글이 없는 상대경로만 보여 준다. 한글 절대경로는 옮겨 적다 깨진다
    rel_dir = f"output/{run_dir.name}"

    # MCP 서버 다섯 개에서 도구를 받아 워커 네 명을 만든다. 파일 서버에는 이번 실행 폴더를 넘긴다
    client = MultiServerMCPClient(mcp_connections(run_dir), tool_name_prefix=True)
    tools = await client.get_tools()
    print("MCP 도구:", len(tools))
    create_workers(tools)

    # 첫 State. turn 과 round 는 0, 누적 필드(analyses, findings, messages)는 비워서 시작한다
    state = {"request": args.request, "run_dir": rel_dir, "next_worker": "", "instruction": "",
             "turn": 0, "round": 0, "plan": [], "analyses": {}, "findings": [], "report_path": "",
             "review": None, "feedback": "", "messages": []}
    # recursion_limit 은 노드 실행 횟수의 상한이다. MAX_TURNS, MAX_ROUNDS 를 다 써도 넘지 않게 넉넉히 준다
    # (데이터 분석 한 번에 supervisor, analysis_planner, data_analyst 세 단계가 든다)
    result = await build_graph().ainvoke(state, {"recursion_limit": 100})

    # 결과 정리: 분석 작업과 워커 방문 순서를 찍고 대화 기록을 messages.json 으로 남긴다. report.md 는 작성자가, status.json 은 끝낸 노드가 저장한다
    print("분석 작업:", list(result["analyses"]))
    visited = [finding["worker"] for finding in result["findings"]]
    print("조사 순서:", " -> ".join(visited))
    (run_dir / "messages.json").write_text(
        json.dumps(messages_to_dict(result["messages"]), ensure_ascii=False, indent=2), encoding="utf-8")
    status_path = run_dir / "status.json"
    if status_path.exists():
        print("상태:", json.loads(status_path.read_text(encoding="utf-8"))["status"])
    report_path = run_dir / "report.md"
    if report_path.exists():
        print("보고서:", report_path)
    else:
        print("보고서 없음: 작성자가 report.md 를 저장하지 못했습니다")


if __name__ == "__main__":
    asyncio.run(main())
