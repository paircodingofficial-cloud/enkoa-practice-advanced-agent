"""실행 층: CLI 진입점. 실행: uv run -m app.main "보고서 기준으로 다음 달 블로그 글 1편과 쇼츠 대본 1편 만들어 줘" """
import asyncio
import sys
from datetime import datetime

from app.agents.workers import create_writer
from app.core.config import OUTPUT_DIR, REPORT_PATH
from app.graph.builder import build_graph
from app.tools.mcp_servers import load_tools


async def main(request: str) -> None:
    """요청 하나로 그래프를 끝까지 실행하고 output/<시각>/ 에 결과를 남긴다."""
    # 그래프를 컴파일하고, 이번 실행의 산출물 폴더를 실행 시각 이름으로 만든다.
    graph = build_graph()
    run_dir = OUTPUT_DIR / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True)
    print("산출물 폴더:", run_dir)

    # 파일 서버의 루트가 이번 실행 폴더라서 폴더를 만든 뒤에 도구를 받는다.
    tools = await load_tools(run_dir)
    for worker, items in tools.items():
        print(f"{worker} 도구:", [item.name for item in items])
    writer = create_writer(tools)

    # 입력 State 의 모든 필드를 처음 값으로 채워 넣는다. context 는 State 에 넣지 않는 실행 자원이다.
    await graph.ainvoke(
        {"request": request, "report": REPORT_PATH.read_text(encoding="utf-8"), "plan": [],
         "findings": {}, "brief": {}, "round": 0, "gap_filled": False, "draft": {}, "review": None, "feedback": "",
         "instruction": ""},
        context={"tools": tools, "run_dir": run_dir, "writer": writer},
    )
    # 파일은 노드들이 이미 썼다. 폴더에 남은 파일 이름만 보여 준다.
    print("저장한 파일:", sorted(p.name for p in run_dir.iterdir()))


if __name__ == "__main__":
    # 첫 번째 명령행 인자를 요청 문장으로 받아 비동기로 실행한다.
    asyncio.run(main(sys.argv[1]))
