"""스키마 층: 그래프를 실행할 때 노드에 넘기는 실행 값(ChatContext)의 모양을 정한다.

판정 객체와 검색기는 State 에 넣지 않는다. State 는 체크포인터가 턴마다 저장하는 대화 기록이고,
판정 객체처럼 저장할 수 없는 큰 객체는 실행할 때 context=ChatContext(...) 로 따로 넘긴다.
"""
from dataclasses import dataclass
from typing import Any


@dataclass
class ChatContext:
    """노드가 runtime.context 로 읽는 실행 값 묶음."""
    rails: Any            # 입력, 출력 레일 판정 객체(LLMRails, rails/guard)
    retriever: Any        # 검색 문서 검색기(Chroma 검색기)
    fan_id: str | None    # 로그인한 팬 id. 로그인하지 않았으면 None 이다(내 티켓, 내 주문을 조회하지 않는다)


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.core.schemas
    # 실제 판정 객체 대신 이름 글자를 넣어 모양만 본다
    sample = ChatContext(rails="rails/guard", retriever="chroma", fan_id="F0001")
    print(sample)
