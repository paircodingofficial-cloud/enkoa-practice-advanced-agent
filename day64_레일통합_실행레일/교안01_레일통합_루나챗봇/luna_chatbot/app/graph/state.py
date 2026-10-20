"""그래프 층: 노드가 읽고 고치는 대화 State 의 모양을 정한다.

messages 는 체크포인터가 대화 ID(thread_id)마다 저장해 다음 턴에 그대로 이어진다.
나머지 칸은 이번 턴의 값이다. input_rail 노드가 턴을 시작할 때 모두 비운다.
"""
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class GuardedChatState(TypedDict):
    """레일을 단 루나 챗봇의 State."""
    # 대화 기록: 노드가 돌려준 메시지를 뒤에 붙이고, 같은 id 면 그 메시지를 바꾼다
    messages: Annotated[list[AnyMessage], add_messages]

    # 이번 턴의 판정 결과(check_input, check_output 이 돌려준 dict). 판정하지 않았으면 빈 dict
    input_check: dict
    output_check: dict
    blocked_by: str        # 막은 레일 흐름 이름(예: jev policy input). 통과하면 빈 문자열
    rule_id: str           # 막은 규칙 id(예: IN-05, OUT-08). 통과하면 빈 문자열

    # 이번 턴의 경로와 검색 기록
    # route: 라우터가 고른 경로(chitchat 일상 대화, venue 공연장, my_ticket, my_order DB 질문,
    #        my_ticket_rule, my_order_rule 내 정보 + 규정 섞인 질문, out_of_scope 업무 밖 질문, rag 검색)
    #        또는 login(로그인하지 않은 팬의 DB 질문, 조회 노드가 바꾼다), refuse(입력 차단)
    route: str
    lookup_text: str       # DB 에서 조회한 정보(공연장, 내 티켓, 내 주문)를 답변 모델에 줄 글로 바꾼 것
    search_query: str      # rewrite_query 노드가 정한 검색어
    retrieved_docs: list   # 검색 문서. retrieval_rail 노드가 숨은 지시가 든 절을 뺀 목록으로 바꾼다
    removed_doc_ids: list  # 검색 레일이 뺀 절 id
    cards: list            # 화면에 그릴 카드. {"type": "venue" | "ticket" | "order" | "blocked", ...}

    # 이번 턴의 다시 만들기 기록(출력 레일이 RETRY_RULES 의 규칙으로 막았을 때만 쓴다)
    retry_count: int       # 이번 턴에 답을 다시 만든 횟수(0 또는 1)
    retry_feedback: str    # 답변 노드가 다음 호출에만 넣을 고칠 점. 답변 노드가 쓰고 나면 비운다


# [보조 함수] 이번 턴 칸 비우기
def empty_turn() -> dict:
    """이번 턴의 칸을 모두 빈 값으로 채운 dict 를 돌려준다(messages 는 넣지 않는다)."""
    return {
        "input_check": {},
        "output_check": {},
        "blocked_by": "",
        "rule_id": "",
        "route": "",
        "lookup_text": "",
        "search_query": "",
        "retrieved_docs": [],
        "removed_doc_ids": [],
        "cards": [],
        "retry_count": 0,
        "retry_feedback": "",
    }


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.state
    print("State 칸:", list(GuardedChatState.__annotations__))
    print("턴 시작 값:", empty_turn())
