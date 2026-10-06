"""에이전트 층: 실행 전에 한 번 만들어 두는 에이전트. 작성자 에이전트를 허용된 도구만으로 create_agent 한다."""
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware

from app.core.config import AGENT_CALL_LIMIT, writer_llm
from app.core.prompts import WRITER_PROMPT
from app.tools.handoff import request_research, request_review


def create_writer(tools: dict[str, list]):
    """파일 쓰기와 핸드오프 도구(검수 요청, 추가 조사 요청)만 가진 작성자 에이전트를 돌려준다."""
    # 작성자는 조사 도구를 모른다. 파일 쓰기와 핸드오프 도구만 줘서 할 수 있는 일을 좁힌다.
    # TODO: 파일 쓰기와 핸드오프 도구만 가진 작성자 에이전트 만들기
    # 1) 도구는 tools["writer"](files_write_file) 에 request_review, request_research 를 더한 목록만 준다. 조사 도구는 주지 않는다
    # 2) 한 응답에 도구 하나만 부르는 writer_llm 을 쓰고, 시스템 프롬프트와 이름(writer)을 준다
    # 3) 모델 호출 상한 미들웨어를 건다(AGENT_CALL_LIMIT 까지만 부르고, 닿으면 에러 없이 끝낸다). 만든 에이전트를 돌려준다
    raise NotImplementedError("TODO를 완성하세요")
