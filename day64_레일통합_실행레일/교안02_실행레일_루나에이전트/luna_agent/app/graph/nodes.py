"""그래프 층: 바깥 그래프의 레일 노드. 노드 하나가 한 가지 일을 하고, 바꿀 State 칸만 dict 로 돌려준다.

흐름: input_rail -> (막힘) refuse -> 끝
                 -> agent(create_agent 와 실행 레일 미들웨어, graph/builder.py) -> output_rail -> 끝
      output_rail 이 다시 쓰면 고쳐질 규칙(core/prompts.py 의 RETRY_RULES)으로 막았고 이번 턴에 아직 다시 쓰지 않았으면
      regenerate -> output_rail 을 한 번 더 돈다. 그 밖의 막힘은 거절 문장으로 끝난다.
판정은 guards/rails.py 의 check_input, check_output(NeMo check_async)이 한다. 로그인 정보는 runtime.context(AgentContext)로 받는다.
"""
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from app.core.config import DOCUMENT_SEPARATOR, llm
from app.core.prompts import AGENT_SYSTEM_PROMPT, RETRY_RULES, format_events
from app.core.schemas import AgentContext
from app.graph.chat import rejection_reason
from app.graph.state import LunaState
from app.guards.rails import BLOCKED_MESSAGE, check_input, check_output, guard_rails
from app.tools.fan_db import list_events


# [보조 함수] 에이전트 시스템 프롬프트
def agent_system_prompt() -> str:
    """시스템 프롬프트 고정 부분 뒤에 DB 공연 목록을 붙인 글을 돌려준다. 에이전트 노드와 다시 쓰기 노드가 같은 글을 쓴다."""
    # 공연 목록을 붙여 두면 팬이 공연 이름으로 물어도 모델이 get_event_venue 에 넘길 공연 id 를 안다
    return AGENT_SYSTEM_PROMPT + "\n\n" + format_events(list_events())


# [보조 함수] 이번 턴의 근거 문서
def turn_documents(messages: list, db_path) -> str:
    """마지막 팬 메시지 뒤의 도구 결과를 이은 근거 문서 글을 돌려준다. 성공한 도구 결과가 있는 턴은 공연 목록을 앞에 붙이고,
    도구를 안 쓴 턴과 도구 결과가 모두 거절(실행 레일의 막힘, 사람 거절, 도구의 업무 규칙 거절)인 턴은 빈 문자열이다."""
    # 1. 도구 결과 모으기: 팬 메시지가 나올 때마다 비우므로 마지막 팬 메시지 뒤의 결과만 남는다
    #    내 티켓, 주문 같은 조회 결과도 근거다. 도구 결과에 없는 날짜나 금액을 지어내면 사실 대조가 막는다
    documents = []
    succeeded = False
    for message in messages:
        if message.type == "human":
            documents = []
            succeeded = False
        if message.type == "tool":
            documents.append(message.text)
            # 오류 결과(status="error")와 {"error": 이유} 결과는 사실이 아니라 거절 이유다. 그 밖의 결과가 하나라도 있어야 성공한 턴이다
            if message.status == "success" and rejection_reason(message.text) == "":
                succeeded = True

    # 2. 거절만 있는 턴: 답은 거절 이유를 전할 뿐이라 대조할 사실이 없다. 근거 문서를 비워 사실 대조만 건너뛴다(출력 정책 판정은 그대로 돈다)
    #    거절 이유를 근거로 넘기면 모델이 풀어 쓴 거절 안내를 사실 대조가 근거 없는 말로 보고 막아,
    #    팬이 "아직 공지로 확인되지 않은 내용" 이라는 엉뚱한 안내(REF-08)를 받는다
    if not succeeded:
        return ""

    # 3. 성공한 결과가 있는 턴: 시스템 프롬프트의 공연 목록(날짜, 공연장)도 근거로 앞에 붙인다. 모델이 그 날짜를 덧붙여도 지어낸 말이 아니다
    #    같은 턴의 거절 이유도 근거에 남는다. 일부만 막힌 턴에서 막힌 이유를 전한 문장이 근거 없는 말로 막히지 않는다
    documents.insert(0, format_events(list_events(db_path)))
    return DOCUMENT_SEPARATOR.join(documents)


# [노드] 입력 레일
async def input_rail(state: LunaState) -> dict:
    """입력 레일 판정 결과(input_verdict)와, 이번 턴을 새로 시작하도록 비운 출력 판정(output_verdict)과 다시 쓰기 횟수(retry_count)를 돌려준다."""
    # 앞선 대화를 함께 넘긴다. NeMo 가 이 대화를 Jev 입력 판정 액션에 함께 넘겨 주어(교안 01 의 events 인자) 여러 메시지에 나눠 보낸 공격도 본다
    verdict = await check_input(guard_rails(), state["messages"])
    # 판정 칸과 횟수는 이번 턴의 값이라, 체크포인터에 남은 앞 턴 값을 여기서 덮어쓴다
    return {"input_verdict": verdict, "output_verdict": {}, "retry_count": 0}


# [노드] 거절
def refuse(state: LunaState) -> dict:
    """막힌 팬 메시지를 표시 문구로 바꾼 같은 id 의 메시지와 거절 문장 AI 메시지를 messages 로 돌려준다."""
    # 같은 id 로 보내면 add_messages 가 그 메시지를 바꾼다. 다음 턴에 공격 문장이 모델에게 다시 가지 않는다
    question = state["messages"][-1]
    return {"messages": [HumanMessage(content=BLOCKED_MESSAGE, id=question.id), AIMessage(content=state["input_verdict"]["content"])]}


# [노드] 출력 레일
async def output_rail(state: LunaState, runtime: Runtime[AgentContext]) -> dict:
    """출력 레일 판정 결과(output_verdict)를 돌려준다. 막혔거나 가렸으면 마지막 답을 바꿀 같은 id 의 메시지(messages)도 함께 돌려준다."""
    # 1. 판정: 마지막 답을 이번 턴의 도구 결과(근거 문서)와 함께 출력 레일에 넘긴다
    answer = state["messages"][-1]
    documents_text = turn_documents(state["messages"], runtime.context.db_path)
    verdict = await check_output(guard_rails(), state["messages"], documents_text)
    update = {"output_verdict": verdict}

    # 2. 막혔거나(blocked) 가렸으면(modified): 답을 거절 문장 또는 개인정보를 가린 답으로 바꾼다(같은 id 라 덮어쓴다)
    #    다시 쓰기로 갈 막힘도 일단 거절 문장으로 바꾼다. 다시 쓰기에 실패해 끝나도 팬에게는 거절 문장이 간다
    if verdict["status"] == "blocked" or verdict["status"] == "modified":
        update["messages"] = [AIMessage(content=verdict["content"], id=answer.id)]

    # 3. 통과(passed): 답을 그대로 두고 판정만 적는다
    return update


# [노드] 답 다시 쓰기
async def regenerate(state: LunaState) -> dict:
    """출력 레일이 막은 답을 한 번 다시 쓴 같은 id 의 메시지(messages)와 1 늘린 다시 쓰기 횟수(retry_count)를 돌려준다."""
    answer = state["messages"][-1]
    feedback = RETRY_RULES[state["output_verdict"]["rule_id"]]

    # 도구 없이 답변 모델만 부른다(에이전트 노드로 돌아가지 않는다). 도구를 다시 실행하면 취소, 환불이 두 번 일어날 수 있다
    # 근거는 대화 기록에 이미 있는 이번 턴의 도구 결과다. 막힌 답(지금은 거절 문장인 마지막 메시지)은 빼고 넘긴다
    # 고칠 점은 이번 호출에만 붙이고 대화 기록에는 남기지 않는다
    prompt = [SystemMessage(content=agent_system_prompt())] + state["messages"][:-1] + [SystemMessage(content=feedback)]
    response = await llm.ainvoke(prompt)

    # 같은 id 로 돌려줘 거절 문장을 새 답으로 덮어쓴다. 새 답은 엣지를 따라 출력 레일을 한 번 더 지난다
    return {"messages": [AIMessage(content=response.text, id=answer.id)], "retry_count": state["retry_count"] + 1}


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.nodes
    # 레일 판정과 답변 모델은 부르지 않는다. 근거 문서 모으기만 확인한다
    from langchain_core.messages import ToolMessage

    from app.core.config import DB_PATH

    sample_messages = [
        HumanMessage("내 티켓 좌석 알려 줘"),
        AIMessage("", tool_calls=[{"name": "get_my_tickets", "args": {}, "id": "call_1"}]),
        ToolMessage('{"tickets": [{"ticket_id": "T00001", "seat": "1층 B구역 7열 12번"}]}', tool_call_id="call_1"),
        AIMessage("1층 B구역 7열 12번이에요."),
    ]
    print("근거 문서:\n" + turn_documents(sample_messages, DB_PATH))
    print("다시 쓰는 규칙:", list(RETRY_RULES))
