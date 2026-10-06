"""도구 층: 기성 MCP 서버 연결 설정과 워커별 허용 도구 목록을 둔다."""
import os
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

# 윈도우는 npx 대신 npx.cmd 를 실행해야 한다.
if sys.platform == "win32":
    NPX = "npx.cmd"
else:
    NPX = "npx"

# 워커마다 쓸 수 있는 도구 이름. 목록에 없는 도구는 그 워커가 존재조차 모른다.
ALLOWED_TOOLS = {
    "naver": ["naver_search_blog", "naver_search_news", "naver_datalab_search"],
    "youtube": ["youtube_searchVideos", "youtube_getVideoDetails", "transcript_get_transcript"],
    "web": ["web_tavily_search"],
    "writer": ["files_write_file"],
}


async def load_tools(run_dir: Path) -> dict[str, list]:
    """워커 이름 -> 허용된 MCP 도구 목록 딕셔너리를 돌려준다. main 에서 한 번만 부른다."""
    # 서버 다섯 개를 한 클라이언트로 묶는다. stdio 는 npx 로 자식 프로세스를 띄워 표준입출력으로 말한다.
    client = MultiServerMCPClient(
        {
            "naver": {
                "command": NPX, "args": ["-y", "@isnow890/naver-search-mcp@1.0.52"], "transport": "stdio",
                "env": {"NAVER_CLIENT_ID": os.environ["NAVER_CLIENT_ID"],
                        "NAVER_CLIENT_SECRET": os.environ["NAVER_CLIENT_SECRET"]},
            },
            "youtube": {
                "command": NPX, "args": ["-y", "youtube-data-mcp-server@1.0.16"], "transport": "stdio",
                "env": {"YOUTUBE_API_KEY": os.environ["YOUTUBE_API_KEY"]},
            },
            "transcript": {
                "command": NPX, "args": ["-y", "@sinco-lab/mcp-youtube-transcript@0.0.12"], "transport": "stdio",
            },
            "web": {
                "command": NPX, "args": ["-y", "tavily-mcp@0.2.22"], "transport": "stdio",
                "env": {"TAVILY_API_KEY": os.environ["TAVILY_API_KEY"]},
            },
            # 파일 서버는 이번 실행 폴더만 연다. 그 밖에는 쓰지 못한다.
            "files": {
                "command": NPX, "args": ["-y", "@modelcontextprotocol/server-filesystem@2026.8.31", str(run_dir)],
                "transport": "stdio",
            },
        },
        tool_name_prefix=True,   # naver_, youtube_, web_, files_ 접두사로 이름 충돌을 막는다
    )
    # MCP 도구는 비동기 전용이라 await 로 받는다. 서버가 가진 도구 전체가 오고, 아래에서 걸러 낸다.
    tools = await client.get_tools()
    # 워커마다 허용 목록에 있는 도구만 담는다.
    by_worker = {}
    for worker, names in ALLOWED_TOOLS.items():
        by_worker[worker] = []
        for item in tools:
            if item.name in names:
                by_worker[worker].append(item)
    return by_worker
