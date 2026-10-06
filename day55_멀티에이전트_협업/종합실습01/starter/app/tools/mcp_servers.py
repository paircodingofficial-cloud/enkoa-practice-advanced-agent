"""도구 층: 기성 MCP 서버 연결 설정과 워커별 허용 도구 목록."""
import logging
import os
import sys
from pathlib import Path

from app.core.config import DB_PATH, PROJECT_DIR

# 코드 실행 서버가 stdout 에 섞어 보내는 안내문 때문에 나는 긴 경고를 끈다(이 모듈을 쓰는 곳 모두에 적용)
logging.getLogger("mcp.client.stdio").setLevel(logging.CRITICAL)

# 윈도우에서는 npx 대신 npx.cmd 를 실행해야 한다
if sys.platform == "win32":
    NPX = "npx.cmd"
else:
    NPX = "npx"

# 워커마다 쓸 수 있는 도구 이름. 목록은 워커가 어떤 도구를 보는지를 정한다.
# 코드 실행 도구는 그 안에서 파일을 쓰거나 DB 를 여는 일도 할 수 있어서, 실제 격리는 컨테이너 같은 샌드박스가 맡는다.
# SQLite 서버의 write_query, create_table 은 목록에서 뺐고, 작성자의 파일 쓰기는 파일 서버가 이번 실행 폴더로 막는다. 핸드오프 도구는 MCP 가 아니라 tools/handoff.py 에 있다.
ALLOWED_TOOLS = {
    "data_analyst": ["db_read_query", "db_list_tables", "db_describe_table", "code_run-code"],
    "doc_reader": ["docs_convert_to_markdown"],
    "web_researcher": ["web_tavily_search"],
    "report_writer": ["files_write_file"],
}


def mcp_connections(run_dir: Path) -> dict:
    """MultiServerMCPClient 에 넘길 서버 다섯 개의 실행 설정을 돌려준다."""
    # 코드 실행 서버가 지금 가상환경의 python 을 찾게 PATH 앞에 붙인다
    child_env = {"PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""),
                 # 윈도우 파이썬도 결과를 UTF-8 로 내보내게 한다(한글이 깨지지 않게)
                 "PYTHONUTF8": "1"}
    # 서버 버전은 고정한다. 최신판이 도구 이름이나 인자를 바꾸면 허용 목록이 조용히 어긋난다
    # 서버 이름(db, code, docs, web, files)이 도구 이름 앞에 붙는다(예: db_read_query)
    return {
        # mcp==1.9.4 를 함께 깔아야 SQLite 서버가 뜬다. 최신 mcp 로는 시작하자마자 죽는다
        "db": {"command": "uvx", "transport": "stdio",
               "args": ["--with", "mcp==1.9.4", "--from", "mcp-server-sqlite", "mcp-server-sqlite",
                        "--db-path", str(DB_PATH)]},
        # 코드를 프로젝트 폴더에서 돌린다. 분석가는 data/x.csv, output/실행시각/x.png 처럼 상대경로만 쓰면 된다
        "code": {"command": NPX, "transport": "stdio", "env": child_env, "cwd": str(PROJECT_DIR),
                 "args": ["-y", "mcp-server-code-runner@0.1.8"]},
        # PDF 를 마크다운 글로 바꿔 주는 서버. 문서 담당자가 쓴다
        "docs": {"command": "uvx", "transport": "stdio", "args": ["markitdown-mcp@0.0.1a7"]},
        # Tavily 웹 검색 서버. .env 에서 읽은 키를 서버의 환경변수로 넘긴다(키가 없으면 여기서 KeyError)
        "web": {"command": NPX, "transport": "stdio", "env": {"TAVILY_API_KEY": os.environ["TAVILY_API_KEY"]},
                "args": ["-y", "tavily-mcp@0.2.22"]},
        # 파일 쓰기는 이번 실행 폴더 안으로만 연다
        "files": {"command": NPX, "transport": "stdio",
                  "args": ["-y", "@modelcontextprotocol/server-filesystem@2026.8.31", str(run_dir)]},
    }
