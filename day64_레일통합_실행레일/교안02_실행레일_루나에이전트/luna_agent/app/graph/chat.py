"""그래프 층: 대화 ID 하나에 팬 메시지 한 턴을 보내고, 멈춘 승인을 이어 가고, 턴 결과를 요약한다.

CLI(main.py), 평가(evaluate.py), 화면(ui/chat_app.py)이 모두 이 함수들로 에이전트를 쓴다(교안 01 graph/chat.py 와 같은 이름).

승인과 이어 가기
1. send_message: 모델이 취소, 환불 도구를 고르면 에이전트 노드 안의 사람 승인(HumanInTheLoopMiddleware)이 실행을 멈춘다.
   멈춘 자리는 바깥 그래프의 체크포인터에 대화 ID(thread_id) 별로 저장되고, 결과의 __interrupt__ 에 승인할 작업 목록이 온다(pending_actions).
   멈춘 동안 바깥 State 의 messages 에는 에이전트 노드 안의 도구 호출이 아직 없다. 그래서 멈춘 에이전트 노드의 State 에서 읽어 바꿔 넣는다.
2. resume_turn: 작업마다 approve 또는 reject 결정을 같은 대화 ID 로 바깥 그래프에 보내면 에이전트 노드 안의 멈춘 자리에서 이어 간다.
   이미 실행된 도구는 다시 돌지 않는다. 이어 간 에이전트가 끝나면 출력 레일 노드까지 돈다.
   reject 를 받은 호출은 실행되지 않고, 거절 문장이 도구 결과(status="error")로 모델에게 간다.
3. 사람 거절은 레일 표시(rail)가 없는 오류라 모델이 도구를 잘못 부른 호출 오류와 모양이 같다.
   그래서 resume_turn 이 거절한 호출 id 를 State(human_rejected_ids)에 적고, summarize_turn 이 그 목록으로 둘을 나눈다.
"""
import json

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from app.core.config import APPROVAL_TOOLS


# [보조 함수] 멈춘 에이전트 노드의 State
async def paused_agent_state(app, config: dict):
    """승인을 기다리며 멈춘 에이전트 노드(서브그래프)의 저장된 State(StateSnapshot)를 돌려준다. 멈춘 실행이 없으면 None 이다."""
    # 바깥 그래프만 읽으면 다음 노드가 agent 라는 것만 보인다. 멈춘 도구 호출 메시지는 에이전트 노드 안의 State 에 있다
    # subgraphs=True: 바깥 그래프의 멈춘 작업(task)마다 그 안의 서브그래프 State 까지 함께 읽어 task.state 에 담는다
    saved = await app.aget_state(config, subgraphs=True)
    for task in saved.tasks:
        # 멈춘 에이전트 노드: 그 안의 State 를 돌려준다
        if task.state is not None:
            return task.state
    # 멈춘 서브그래프가 없음(승인 대기가 아니거나 이미 끝난 턴)
    return None


# [보조 함수] 그래프 한 번 실행
async def run_graph(app, graph_input, config: dict, context) -> dict:
    """바깥 그래프를 실행한 결과를 돌려준다. 승인으로 멈췄으면 messages 를 멈춘 에이전트 노드의 메시지로 바꿔 넣는다."""
    result = await app.ainvoke(graph_input, config=config, context=context)
    # 승인 대기로 멈춤: 에이전트 노드가 끝나야 그 안의 메시지가 바깥 messages 에 합쳐진다
    # 멈춘 동안의 도구 호출은 노드 안의 State 에만 있으므로, 그 메시지로 바꿔 넣어야 요약이 승인 대기 호출을 본다
    if pending_actions(result):
        result["messages"] = (await paused_agent_state(app, config)).values["messages"]
    # 끝까지 돈 턴(또는 바꿔 넣은 멈춘 턴)의 결과
    return result


# [보조 함수] 한 턴 보내기
async def send_message(app, thread_id: str, text: str, context) -> dict:
    """대화 ID 하나에 팬 메시지 하나를 보내고, 그 턴이 끝났을 때(또는 승인을 기다리며 멈췄을 때)의 결과를 돌려준다."""
    # 같은 thread_id 로 보내면 체크포인터가 앞 턴의 messages 를 꺼내 이 메시지 앞에 붙여 준다
    config = {"configurable": {"thread_id": thread_id}}
    return await run_graph(app, {"messages": [HumanMessage(content=text)]}, config, context)


# [보조 함수] 사람이 거절한 도구 호출 id
def rejected_call_ids(messages: list, actions: list, decisions: list) -> list:
    """승인 대기 작업과 사람의 결정을 순서대로 짝지어, reject 결정을 받은 작업의 도구 호출 id 목록을 돌려준다."""
    # 승인 대기 작업에는 호출 id 가 없다. 작업은 멈춘 AI 메시지(마지막 메시지)의 도구 호출 순서대로 오므로
    # 앞에서부터 이름과 인자가 같은 호출을 하나씩 짝짓는다(같은 호출이 두 번 있어도 한 호출을 두 작업에 쓰지 않는다)
    calls = messages[-1].tool_calls
    paired_ids = []
    rejected_ids = []
    for action, decision in zip(actions, decisions):
        for call in calls:
            # 아직 짝짓지 않았고 이름과 인자가 같은 첫 호출이 이 작업의 호출이다
            if call["id"] not in paired_ids and call["name"] == action["name"] and call["args"] == action["args"]:
                paired_ids.append(call["id"])
                # 거절 결정이면 그 호출 id 를 적는다(승인은 적지 않는다)
                if decision["type"] == "reject":
                    rejected_ids.append(call["id"])
                break
    return rejected_ids


# [보조 함수] 멈춘 승인 이어 가기
async def resume_turn(app, thread_id: str, decisions: list, context) -> dict:
    """승인을 기다리며 멈춘 실행에 사람의 결정(approve, reject) 목록을 넘겨 이어 간 결과를 돌려준다(send_message 와 같은 모양)."""
    # 멈춘 실행은 바깥 그래프의 체크포인터에 thread_id 로 저장돼 있다. 결정 순서는 승인 대기 작업 순서와 같아야 한다
    config = {"configurable": {"thread_id": thread_id}}

    # 1. 이어 가기 전에 저장된 멈춘 자리를 읽어, 거절 결정을 받은 호출 id 를 찾는다
    #    승인 작업 목록(interrupts)은 바깥 그래프에서, 멈춘 도구 호출 메시지는 에이전트 노드 안의 State 에서 읽는다
    saved = await app.aget_state(config)
    actions = pending_actions({"__interrupt__": saved.interrupts})
    agent_state = await paused_agent_state(app, config)
    rejected_ids = rejected_call_ids(agent_state.values["messages"], actions, decisions)

    # 2. 이어 가기: Command 는 바깥 그래프에 보내지만, LangGraph 가 멈춘 에이전트 노드 안의 승인 미들웨어까지 결정을 전한다
    #    resume: 승인 미들웨어가 받을 결정. approve 는 도구를 실행하고, reject 는 거절 문장을 오류 도구 결과로 모델에게 준다
    #    update: 거절한 호출 id 를 바깥 State 에 더한다. 화면과 평가가 사람 거절을 도구 오류와 나눠 보려고 적는다
    #    이어 간 에이전트가 답을 내면 바깥 그래프의 엣지를 따라 출력 레일 노드까지 돈다
    command = Command(resume={"decisions": decisions}, update={"human_rejected_ids": rejected_ids})
    return await run_graph(app, command, config, context)


# [보조 함수] 이번 턴의 메시지
def current_turn(messages: list) -> list:
    """대화 기록에서 마지막 팬(사람) 메시지와 그 뒤의 메시지를 돌려준다."""
    # 팬 메시지가 나올 때마다 시작 위치를 옮기므로 마지막 팬 메시지의 위치가 남는다
    start = 0
    for index, message in enumerate(messages):
        if message.type == "human":
            start = index
    return messages[start:]


# [보조 함수] 도구의 업무 규칙 거절
def rejection_reason(content: str) -> str:
    """도구 결과가 {"error": 이유} 모양의 JSON 글이면 이유를, 아니면 빈 문자열을 돌려준다."""
    # 예매, 주문 도구는 dict 를 돌려주고 langchain 이 JSON 글로 바꾼다. 검색 문서, 안내 문장은 { 로 시작하지 않는다
    if not content.startswith("{"):
        return ""
    data = json.loads(content)
    # 업무 규칙 거절: 도구가 넣은 이유 문장
    if "error" in data:
        return data["error"]
    # 정상 결과 dict(예: {"tickets": [...]})
    return ""


# [보조 함수] 도구 호출과 결과 짝짓기
def tool_events(messages: list, rejected_ids: list) -> list:
    """이번 턴의 도구 호출마다 {name, args, status, content, rail, rule_id, artifact, human_rejected} 를 돌려준다."""
    turn = current_turn(messages)

    # 도구 결과(ToolMessage)를 호출 id 로 찾을 수 있게 모은다
    results = {}
    for message in turn:
        if message.type == "tool":
            results[message.tool_call_id] = message

    # 모델이 낸 도구 호출 순서대로 결과를 붙인다
    # status: success(실행됨), rejected(도구가 업무 규칙으로 거절해 바꾼 것 없음),
    #         error(실행 레일이 막음, 사람이 거절함, 모델이 인자를 빠뜨리는 등 잘못 부른 도구 호출 오류),
    #         pending(결과가 없음: 승인 대기, 또는 같은 메시지의 승인을 기다려 아직 실행 안 함)
    events = []
    for message in turn:
        if message.type != "ai":
            continue
        for call in message.tool_calls:
            event = {"name": call["name"], "args": call["args"], "status": "pending", "content": "",
                     "rail": "", "rule_id": "", "artifact": None, "human_rejected": call["id"] in rejected_ids}
            # 결과가 있는 호출만 상태를 채운다. 결과가 없으면 pending 그대로 둔다
            if call["id"] in results:
                result = results[call["id"]]
                event["status"] = result.status
                event["content"] = result.text
                event["artifact"] = result.artifact
                # 실행 레일이 남긴 표시(막은 미들웨어 이름, 규칙 id). 없으면 빈 문자열로 둔다
                if "rail" in result.response_metadata:
                    event["rail"] = result.response_metadata["rail"]
                    event["rule_id"] = result.response_metadata["rule_id"]

            # 실행은 됐지만 도구가 {"error": ...} 로 거절했으면 업무가 끝난 것이 아니다(예: 이미 예매된 좌석)
            if event["status"] == "success" and rejection_reason(event["content"]) != "":
                event["status"] = "rejected"
            events.append(event)
    return events


# [보조 함수] 사람 거절인지
def is_human_rejection(event: dict) -> bool:
    """도구 결과가 상담원이 승인을 거절한 것이면 True 를 돌려준다."""
    # 레일 표시가 없는 오류는 도구 호출 오류(인자 누락 등)일 수도 있다. 거절 문장과 상관없이 resume_turn 이 적어 둔 호출 id 로 가린다
    return event["status"] == "error" and event["human_rejected"]


# [보조 함수] 사람 승인을 기다리는 호출인지
def waits_for_approval(event: dict) -> bool:
    """결과가 없는 호출이 승인 도구라 사람 승인을 기다리는 것이면 True 를 돌려준다."""
    # 사람 승인은 AI 메시지 하나의 도구 실행을 모두 멈춘다. 같은 메시지의 조회 도구도 결과가 없지만 승인 대상은 아니다
    return event["status"] == "pending" and event["name"] in APPROVAL_TOOLS


# [보조 함수] 승인 대기 작업
def pending_actions(result: dict) -> list:
    """실행이 사람 승인을 기다리며 멈췄으면 승인할 작업 목록(name, args, description)을, 아니면 빈 목록을 돌려준다."""
    # 멈추지 않음: 끝까지 돈 실행 결과에는 __interrupt__ 칸이 없고,
    # 저장된 대화 상태(aget_state)의 interrupts 를 넘기면 멈춘 실행이 없을 때 빈 튜플이 온다
    if "__interrupt__" not in result or len(result["__interrupt__"]) == 0:
        return []
    # 멈춤: 승인 미들웨어(HumanInTheLoopMiddleware)가 interrupt 하나에 승인할 작업을 모두 담는다
    return result["__interrupt__"][0].value["action_requests"]


# [보조 함수] 턴 결과 요약
def summarize_turn(result: dict) -> dict:
    """그래프 실행 결과 하나를 요약한 dict 를 돌려준다.

    answer: 팬에게 보낼 답(승인 대기면 빈 문자열), tool_events: 도구 호출마다의 결과(tool_events 참고),
    pending: 승인을 기다리는 작업 목록, input_verdict, output_verdict: 레일 판정(그 레일이 돌지 않았으면 빈 dict),
    blocked_by, rule_id: 처음 막은 레일과 규칙 id(막지 않았으면 빈 문자열), retry_count: 출력 레일이 막은 답을 다시 쓴 횟수
    """
    messages = result["messages"]
    # 사람이 거절한 호출 id(LunaState 칸). 이 대화에서 아직 아무것도 거절하지 않았으면 칸이 없다
    rejected_ids = []
    # 거절한 적이 있으면 State 의 목록을 쓴다
    if "human_rejected_ids" in result:
        rejected_ids = result["human_rejected_ids"]
    events = tool_events(messages, rejected_ids)
    pending = pending_actions(result)

    # 레일 판정 칸은 입력 레일 노드가 돈 뒤에만 있다. 다시 쓰기 횟수도 입력 레일 노드가 0 으로 둔다
    input_verdict = {}
    if "input_verdict" in result:
        input_verdict = result["input_verdict"]
    output_verdict = {}
    if "output_verdict" in result:
        output_verdict = result["output_verdict"]
    retry_count = 0
    if "retry_count" in result:
        retry_count = result["retry_count"]

    # 막은 자리: 입력 레일 -> 실행 레일 -> 출력 레일 순서로 처음 막은 레일 하나를 고른다
    # 사람 거절, 도구 호출 오류(rail 없음)와 도구의 업무 규칙 거절(rejected)은 레일이 막은 것이 아니라 넣지 않는다
    blocked_by = ""
    rule_id = ""
    # 1. 입력 레일이 막았으면 그것이 처음 막은 자리다(이때는 도구도 출력 레일도 돌지 않았다)
    if input_verdict and input_verdict["status"] == "blocked":
        blocked_by = input_verdict["blocked_by"]
        rule_id = input_verdict["rule_id"]
    # 2. 아직 없으면 실행 레일이 막은 첫 도구 호출(표시 rail 이 있는 오류)
    for event in events:
        if blocked_by == "" and event["status"] == "error" and event["rail"] != "":
            blocked_by = event["rail"]
            rule_id = event["rule_id"]
    # 3. 그래도 없으면 출력 레일의 막힘. 다시 쓴 답이 통과했으면 output_verdict 는 통과라 넣지 않는다
    if blocked_by == "" and output_verdict and output_verdict["status"] == "blocked":
        blocked_by = output_verdict["blocked_by"]
        rule_id = output_verdict["rule_id"]

    # 마지막 메시지가 도구 호출 없는 AI 답변이면 그것이 팬에게 보낼 답이다(승인 대기 중이면 아직 답이 없다)
    answer = ""
    last = messages[-1]
    # 승인 대기면 마지막 메시지가 도구 호출을 든 AI 메시지라 답이 빈 문자열로 남는다
    if last.type == "ai" and not last.tool_calls:
        answer = last.text
    return {
        "answer": answer, "tool_events": events, "pending": pending,
        "input_verdict": input_verdict, "output_verdict": output_verdict,
        "blocked_by": blocked_by, "rule_id": rule_id, "retry_count": retry_count,
    }


# [보조 함수] 화면용 판정 기록
def rail_trace(summary: dict) -> dict:
    """summarize_turn 결과를 화면의 레일 판정 기록 {단계 이름: {status, blocked_by, rule_id, detail}} 로 바꿔 돌려준다.

    status 는 passed(통과), modified(가림), blocked(막음), info(레일 판정이 아닌 안내) 가운데 하나다.
    """
    trace = {}
    # 입력 레일이 돈 턴만 그 단계를 넣는다
    if summary["input_verdict"]:
        trace["입력 레일"] = summary["input_verdict"]

    # 도구마다 실행 레일 결과: 실행됨은 통과, 막힘은 막은 미들웨어와 규칙, 숨은 지시를 뺐으면 가림
    # 표시(rail) 없는 오류 결과는 사람 거절이거나 도구 호출 오류다. 레일이 막은 것과 나눠 info 로 둔다
    for index, event in enumerate(summary["tool_events"]):
        stage = f"도구 {index + 1}. {event['name']}"
        # 기본: 실행됨(success)은 통과
        row = {"status": "passed", "blocked_by": event["rail"], "rule_id": event["rule_id"], "detail": ""}
        # 실행 레일이 막음: 막은 이유 문장을 보여 준다
        if event["status"] == "error" and event["rail"] != "":
            row["status"] = "blocked"
            row["detail"] = event["content"]
        # 표시 없는 오류: 도구 호출 오류로 적고, 사람 거절이면 아래에서 문구만 바꾼다
        if event["status"] == "error" and event["rail"] == "":
            row["status"] = "info"
            row["detail"] = "도구 실행 오류: " + event["content"]
        if is_human_rejection(event):
            row["detail"] = "사람이 거절함"
        # 도구가 업무 규칙으로 거절: 레일이 막은 것이 아니라 안내로 둔다
        if event["status"] == "rejected":
            row["status"] = "info"
            row["detail"] = "도구가 업무 규칙으로 거절: " + rejection_reason(event["content"])
        # 결과 없음: 같은 메시지의 다른 호출이 승인을 기다려 아직 실행되지 않았고, 승인 도구면 문구만 바꾼다
        if event["status"] == "pending":
            row["status"] = "info"
            row["detail"] = "같은 메시지의 승인을 기다리는 중(아직 실행 안 함)"
        if waits_for_approval(event):
            row["detail"] = "사람 승인 대기"
        # 규정 검색 결과에서 숨은 지시가 든 절을 뺐으면 가림으로 둔다
        if event["rail"] == "check_tool_result":
            row["status"] = "modified"
            row["detail"] = "숨은 지시가 든 절을 뺌"
        trace[stage] = row

    # 출력 레일이 막은 답을 다시 썼으면 그 단계를 남긴다. 출력 레일 칸은 다시 쓴 답의 판정이다
    if summary["retry_count"] > 0:
        trace["답 다시 쓰기"] = {"status": "info", "blocked_by": "", "rule_id": "", "detail": "출력 레일이 막은 답을 도구 없이 한 번 다시 씀"}
    # 출력 레일이 돈 턴만 그 단계를 넣는다(입력 레일이 막았거나 승인 대기면 없다)
    if summary["output_verdict"]:
        trace["출력 레일"] = summary["output_verdict"]
    return trace


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.chat
    # 모델을 부르지 않고 손으로 만든 실행 결과로 요약을 확인한다
    from langchain_core.messages import AIMessage, ToolMessage

    sample = {
        "messages": [
            HumanMessage("티켓 T00003 취소하고 T00004 좌석은 1층 A구역 1열 14번으로 바꿔 줘."),
            AIMessage("", tool_calls=[
                {"name": "cancel_ticket", "args": {"ticket_id": "T00003"}, "id": "call_1"},
                {"name": "change_seat", "args": {"ticket_id": "T00004", "new_seat": "1층 A구역 1열 14번"}, "id": "call_2"},
            ]),
            ToolMessage("로그인한 팬 본인의 티켓만 처리할 수 있어요.", tool_call_id="call_1", name="cancel_ticket",
                        status="error", response_metadata={"rail": "check_tool_permission", "rule_id": "IN-05"}),
            ToolMessage('{"error": "1층 A구역 1열 14번 은 이미 예매된 좌석이에요."}', tool_call_id="call_2", name="change_seat"),
            AIMessage("본인 티켓만 취소할 수 있고, 그 좌석은 이미 예매됐어요."),
        ],
        "input_verdict": {"status": "passed", "blocked_by": "", "rule_id": "", "content": ""},
        "output_verdict": {"status": "passed", "blocked_by": "", "rule_id": "", "content": ""},
    }
    summary = summarize_turn(sample)
    print("답:", summary["answer"], "/ 막은 자리:", summary["blocked_by"], summary["rule_id"])
    for each_event in summary["tool_events"]:
        print("도구:", each_event["name"], "->", each_event["status"])
    print("판정 기록:", rail_trace(summary))
