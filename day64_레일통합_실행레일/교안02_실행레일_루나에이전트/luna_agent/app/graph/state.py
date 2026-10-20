"""그래프 층: 바깥 그래프(레일 노드 + 에이전트 노드)가 읽고 고치는 대화 State 의 모양을 정한다.

messages 는 체크포인터가 대화 ID(thread_id)마다 저장해 다음 턴에 그대로 이어진다. 에이전트 노드(create_agent)와 같은 이름의 칸이라
에이전트가 쌓은 도구 호출, 도구 결과, 답변이 이 칸에 함께 남는다.
판정 칸과 다시 쓰기 횟수는 이번 턴의 값이다. input_rail 노드가 턴을 시작할 때 비운다.
"""
import operator
from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class LunaState(TypedDict):
    """레일 노드를 단 루나 에이전트의 State."""
    # 대화 기록: 노드가 돌려준 메시지를 뒤에 붙이고, 같은 id 면 그 메시지를 바꾼다
    messages: Annotated[list[AnyMessage], add_messages]

    # 이번 턴의 판정 결과 {status, blocked_by, rule_id, content}. output_verdict 는 입력 레일이 막은 턴에 빈 dict
    input_verdict: dict
    output_verdict: dict
    # 이번 턴에 출력 레일이 막은 답을 다시 쓴 횟수. 한 번만 다시 쓴다(graph/edges.py 의 route_after_output)
    retry_count: int

    # 사람이 거절한 도구 호출 id. graph/chat.py 의 resume_turn 이 이어 갈 때 더한다
    # operator.add 로 이어 붙여 대화가 끝날 때까지 쌓인다. 한 턴에 승인을 두 번 이어 가도 앞의 거절이 남는다
    human_rejected_ids: NotRequired[Annotated[list, operator.add]]


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.state
    print("State 칸:", list(LunaState.__annotations__))
