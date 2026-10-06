"""에이전트 층: 워커 네 명을 각자 허용된 MCP 도구만으로 create_agent 해 둔다."""
import asyncio

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, wrap_tool_call

from app.core.config import WORKER_CALL_LIMIT, llm, writer_llm
from app.core.prompts import WORKER_PROMPTS
from app.tools.handoff import request_research, request_review
from app.tools.mcp_servers import ALLOWED_TOOLS

WORKERS = {}   # 워커 이름 -> 에이전트. main 에서 MCP 도구를 받은 뒤 채운다

# 코드 실행 서버는 코드를 항상 같은 임시 파일에 쓴다. 분석가 여럿이 동시에 부르면 서로의 코드를 덮어쓰므로 한 번에 하나씩 보낸다
code_lock = asyncio.Lock()


# [미들웨어] 코드 실행 도구 호출을 한 번에 하나씩 처리한다
# 이유: 분석가가 Send 로 동시에 돌면 코드 실행 서버의 같은 임시 파일을 서로 덮어써 엉뚱한 결과가 나온다.
#       MCP 서버 코드는 고칠 수 없으니, 에이전트가 도구를 부르는 길목에서 미들웨어로 줄을 세운다.
@wrap_tool_call
async def one_code_at_a_time(request, handler):
    """code_run-code 호출만 잠금 안에서 실행하고 나머지 도구는 그대로 실행한다."""
    if request.tool_call["name"] == "code_run-code":
        async with code_lock:
            return await handler(request)
    return await handler(request)


def create_workers(tools: list) -> None:
    """MCP 도구 전체에서 워커별 허용 도구만 골라 WORKERS 를 채운다(반환값 없음)."""
    # TODO: 워커마다 허용 도구만 골라 create_agent 로 만들고 WORKERS 에 넣기
    # 1) 도구 이름으로 도구를 찾을 수 있게 이름을 키로 하는 딕셔너리를 만든다
    # 2) ALLOWED_TOOLS 를 (워커 이름, 허용 도구 이름 목록)으로 돌며 1)의 딕셔너리에서 그 도구들을 꺼내 리스트로 만든다. 3), 4)도 이 for 안에서 한다
    # 3) report_writer 만 다르다. 도구에 핸드오프 도구 둘(request_review, request_research)을 더하고, 한 응답에 도구 하나만 부르는 writer_llm 을 쓴다
    # 4) 모델, 도구, 시스템 프롬프트(WORKER_PROMPTS), 이름, 미들웨어 두 개로 에이전트를 만들어 WORKERS 에 넣는다
    #    미들웨어: ModelCallLimitMiddleware(모델 호출이 WORKER_CALL_LIMIT 번에 닿으면 에러 없이 멈춘다), one_code_at_a_time
    raise NotImplementedError("TODO를 완성하세요")
