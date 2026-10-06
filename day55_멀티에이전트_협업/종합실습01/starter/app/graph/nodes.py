"""그래프 층: 슈퍼바이저, 분석 계획, 분석가, 워커, 보고서 작성, 검수 노드."""
import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command

from app.agents.workers import WORKERS
from app.core.config import (
    MAX_ROUNDS,
    MAX_TASKS,
    MAX_TURNS,
    PASS_SCORE,
    PROJECT_DIR,
    llm,
)
from app.core.judge import judge_enough, judge_report
from app.core.prompts import (
    ANALYST_INPUT,
    CHANNEL_GUIDES,
    PLANNER_INPUT,
    PLANNER_PROMPT,
    REVIEWER_PROMPT,
    REWORK_PROMPT,
    SUPERVISOR_PROMPT,
    WRITE_REPORT_AT_CAP,
    WRITE_REPORT_INSTRUCTION,
)
from app.core.schemas import AnalysisPlan, NextStep, ReworkStep
from app.graph.state import AnalysisInput, TeamState


# [보조 함수] 모든 보고 모으기: 분석 결과와 워커 보고를 {worker, result} 목록 하나로 묶는다
def all_reports(state: TeamState) -> list[dict]:
    """분석 결과(task_id 순)와 워커 보고(턴 순)를 Jev 판정에 넘길 목록 하나로 돌려준다."""
    reports = []
    for task_id, analysis in state["analyses"].items():
        reports.append({"worker": "data_analyst", "result": f"[분석 {task_id}] {analysis['question']}\n{analysis['result']}"})
    for finding in state["findings"]:
        reports.append({"worker": finding["worker"], "result": finding["result"]})
    return reports


# [보조 함수] LLM 컨텍스트 만들기: 요청, 산출물 폴더, 지금까지의 분석과 보고를 슈퍼바이저와 워커가 읽을 글 하나로 묶는다
def team_notes(state: TeamState) -> str:
    """요청, 산출물 폴더, 분석 결과, 워커 보고를 묶은 글을 돌려준다."""
    # 요청과 폴더를 맨 앞에 두고, 분석 결과와 워커 보고를 이어 붙인다
    lines = [f"요청: {state['request']}", f"산출물 폴더: {state['run_dir']}"]
    for task_id, analysis in state["analyses"].items():
        lines.append(f"[분석 {task_id}] {analysis['question']}\n{analysis['result']}")
    for finding in state["findings"]:
        lines.append(f"[{finding['turn']}턴 {finding['worker']}]\n{finding['result']}")
    return "\n\n".join(lines)


# [보조 함수] 상태 기록: 끝난 상태(통과, 라운드 상한 도달)를 산출물 폴더의 status.json 에 남긴다
def save_status(state: TeamState, status: str, review: dict, feedback: str) -> None:
    """실행이 어떻게 끝났는지와 이번 결정의 검수 판정, 피드백을 status.json 으로 저장한다."""
    # 이번 판정(review, feedback)은 노드가 Command 를 돌려준 뒤에야 State 에 들어가므로 노드가 직접 넘긴다
    record = {"status": status, "round": state["round"], "turn": state["turn"],
              "review": review, "feedback": feedback}
    path = PROJECT_DIR / state["run_dir"] / "status.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


# [보조 함수] 보고서 작성 보내기: 보고서를 쓰라는 지시문을 담아 report_writer 로 가는 Command 를 만든다
def report_command(state: TeamState, instruction: str) -> Command:
    """report_writer 로 가는 Command 를 돌려준다. update 는 next_worker, instruction, turn + 1, 기록용 AIMessage 다."""
    return Command(
        goto="report_writer",
        update={"next_worker": "report_writer", "instruction": instruction, "turn": state["turn"] + 1,
                "messages": [AIMessage(instruction, name="supervisor")]},
    )


# [노드] 슈퍼바이저: 끝낼지, 보고서로 넘길지는 if 문(가드)이 먼저 정하고, 그 밖의 경우에만 GPT 가 다음 담당자를 고른다
async def supervisor(state: TeamState) -> Command:
    """다음 담당자와 지시문을 정해 그 노드로 가는 Command 를 돌려준다(라운드 상한이면 END)."""
    # TODO: 처리할 반려(검수 반려 또는 작성자의 추가 조사 요청)가 있으면 반려 횟수 상한을 확인하고, GPT 로 다음 담당자와 지시문을 정한다
    # 1) state["review"] 가 있을 때만 아래를 한다. round(반려를 처리한 횟수)가 MAX_ROUNDS 이상이면
    #    save_status 에 "라운드 상한 도달: 사람 확인 필요" 와 State 의 review, feedback 을 넘겨 남기고 Command(goto=END) 로 끝낸다
    # 2) 아니면 ReworkStep 구조화 출력으로 다음 담당자와 지시문을 받는다. 시스템 메시지는 REWORK_PROMPT,
    #    사람 메시지는 "[피드백]" 줄과 피드백, 빈 줄, "[팀 기록]" 줄과 team_notes(state) 를 이은 글이다
    # 3) goto 는 고른 담당자, update 는 State 에 쓸 값이다
    #    next_worker, instruction, turn + 1, round + 1, review 는 None(처리했으니 비운다), 기록용 AIMessage 를 넣는다
    raise NotImplementedError("TODO를 완성하세요")

    # TODO: 일을 맡긴 횟수가 상한에 닿았거나 근거가 충분하면 GPT 를 부르지 않고 report_writer 에게 보낸다
    # 1) turn 이 MAX_TURNS 이상이면 Jev 도 부르지 않고 report_command 에 WRITE_REPORT_AT_CAP 지시문을 넘겨 돌려준다
    # 2) 아니면 judge_enough 에 요청과 all_reports(state) 를 넘겨 보고서를 쓸 만큼 근거가 모였을 확률을 받는다
    # 3) 확률이 0.5 이상이면 report_command 에 WRITE_REPORT_INSTRUCTION 지시문을 넘겨 돌려준다
    #    1), 3) 모두 돌려주기 전에 "supervisor:" 로 시작하는 한 줄을 출력한다
    raise NotImplementedError("TODO를 완성하세요")

    # TODO: GPT 구조화 출력으로 다음 담당자와 지시문을 한 번에 받아 Command(goto) 로 보낸다
    # 1) llm 에 NextStep 구조화 출력을 걸고, 시스템 메시지(SUPERVISOR_PROMPT)와 사람 메시지(팀 기록)를 넣어 호출한다
    # 2) goto 는 고른 담당자, update 는 State 에 쓸 값이다
    #    next_worker, instruction, turn + 1, 기록용 AIMessage(지시문, name="supervisor") 네 가지를 넣는다
    raise NotImplementedError("TODO를 완성하세요")


# [노드] 분석 계획: 슈퍼바이저의 지시를 채널별 분석 작업으로 나눈다. 갈 곳은 dispatch 가 정한다
async def analysis_planner(state: TeamState) -> dict:
    """분석 작업 목록(plan)을 만들어 State 에 쓸 값으로 돌려준다."""
    # 이미 분석한 채널을 알려 주어 같은 채널을 되풀이하지 않게 한다
    done = list(state["analyses"])
    if not done:
        done = "없음"
    message = PLANNER_INPUT.format(request=state["request"], instruction=state["instruction"], done=done)
    plan = await llm.with_structured_output(AnalysisPlan).ainvoke([
        SystemMessage(PLANNER_PROMPT.format(max_tasks=MAX_TASKS)),
        HumanMessage(message),
    ])

    # task_id 는 모델에 맡기지 않고 채널로 만든다. 같은 채널을 다시 분석하면 리듀서가 그 키의 값만 새 결과로 바꾼다
    tasks = []
    seen = []
    for item in plan.tasks:
        if item.channel in seen:
            continue
        if len(tasks) >= MAX_TASKS:
            break
        seen.append(item.channel)
        task = item.model_dump()
        task["task_id"] = item.channel
        tasks.append(task)
    print("analysis_planner:", len(tasks), "개 작업", seen)
    return {"plan": tasks}


# [노드] 분석가: Send 로 분석 작업마다 하나씩 병렬 실행한다. 결과는 task_id 를 키로 analyses 에 모인다
async def data_analyst(state: AnalysisInput) -> dict:
    """분석 작업 하나를 분석가 에이전트로 실행하고 {task_id: 결과} 를 돌려준다."""
    # Send 가 넘긴 작업 한 건을 꺼내 채널 안내와 함께 분석가에게 준다
    task = state["task"]
    print("data_analyst:", task["task_id"], task["question"][:50])
    message = ANALYST_INPUT.format(task_id=task["task_id"], channel=task["channel"], guide=CHANNEL_GUIDES[task["channel"]],
                                   question=task["question"], run_dir=state["run_dir"])
    result = await WORKERS["data_analyst"].ainvoke({"messages": [HumanMessage(message)]})
    answer = result["messages"][-1].text
    analysis = {"channel": task["channel"], "question": task["question"], "result": answer}
    return {"analyses": {task["task_id"]: analysis}, "messages": result["messages"][1:]}


# [노드] 워커: doc_reader 와 web_researcher 가 이 함수 하나를 함께 쓰고, 일을 마치면 항상 supervisor 로 돌아간다
async def worker(state: TeamState) -> Command:
    """슈퍼바이저가 고른 워커를 실행하고, 결과를 담아 supervisor 로 돌아가는 Command 를 돌려준다."""
    # 누가 일할지는 State 의 next_worker 가 정한다
    name = state["next_worker"]
    # TODO: 지시문과 팀 기록으로 에이전트를 실행하고 결과를 findings 에 붙여 supervisor 로 돌아간다
    # 1) WORKERS[name] 에이전트에 사람 메시지 하나를 넣어 호출한다. 내용은 지시문 뒤에 빈 줄, "[팀 기록]" 줄, team_notes(state) 를 이어 붙인 글
    # 2) 마지막 메시지의 .text 가 워커의 보고다. 앞부분만 한 줄로 출력한다
    # 3) goto 는 "supervisor", update 는 State 에 쓸 값이다
    # 4) findings 에는 이번 보고(turn, worker, result) 하나만 리스트로 담는다. 리듀서가 기존 보고 뒤에 이어 붙인다
    #    messages 에는 에이전트 결과 메시지에서 맨 앞 입력을 뺀 [1:] 만 넣는다
    raise NotImplementedError("TODO를 완성하세요")


# [노드] 보고서 작성: 검수로 넘기는 일은 작성자 에이전트의 핸드오프 도구가 합니다.
async def report_writer(state: TeamState) -> Command:
    """작성자 에이전트를 실행하고, 검수 요청 없이 끝났으면 reviewer 로 가는 Command 를 돌려준다."""
    # 지시문, 피드백, 앞 보고서, 팀 기록을 한 메시지로 묶는다. 피드백과 앞 보고서는 다시 쓰기일 때만 있다
    parts = [state["instruction"]]
    if state["feedback"]:
        parts.append(f"[검수 피드백]\n{state['feedback']}")
        report_file = PROJECT_DIR / state["run_dir"] / "report.md"
        if report_file.exists():
            parts.append(f"[이전 보고서]\n{report_file.read_text(encoding='utf-8')}")
    parts.append(f"[팀 기록]\n{team_notes(state)}")
    # 작성자가 핸드오프 도구(request_review, request_research)를 부르면 그 자리에서 다음 노드로 넘어가 아래 줄은 실행되지 않는다
    await WORKERS["report_writer"].ainvoke({"messages": [HumanMessage("\n\n".join(parts))]})
    # 검수 요청을 빠뜨리고 끝났어도 그래프가 조용히 끝나지 않게 reviewer 로 넘긴다
    print("report_writer:", "검수 요청 없이 끝나 reviewer 로 넘김")
    return Command(goto="reviewer", update={"report_path": "report.md"})


# [노드] 검수: Jev 판정으로 통과를 정하고, 반려면 피드백을 붙여 supervisor 로 보낸다
async def reviewer(state: TeamState) -> Command:
    """보고서를 판정해 통과면 END 로, 반려면 피드백과 함께 supervisor 로 가는 Command 를 돌려준다."""
    # 작성자가 넘긴 이름이 경로 모양이어도 파일 이름만 써서 이번 실행 폴더에서 읽는다
    report_file = PROJECT_DIR / state["run_dir"] / Path(state["report_path"]).name
    if not report_file.exists():
        print("reviewer:", "보고서 파일 없음")
        return Command(goto="supervisor", update={"review": {"passed": False},
                                                  "feedback": "report.md 가 저장되지 않았다. 보고서를 다시 써서 저장해야 한다."})
    report = report_file.read_text(encoding="utf-8")
    # TODO: Jev 판정으로 통과를 정하고, 반려면 GPT 피드백을 붙여 supervisor 로 보내기
    # 1) judge_report 에 보고서와 all_reports(state) 를 넘겨 점수 두 개(source_fidelity, usefulness)와 보고서가 findings 와 어긋날 확률(contradiction)을 받는다
    # 2) 어긋날 확률이 0.5 미만이고 두 점수가 모두 PASS_SCORE 이상이면 통과다. 판정에 passed 를 더해 review 로 둔다
    # 3) 통과면 save_status 에 "통과", 이번 review, 빈 피드백 "" 을 넘겨 남기고 Command(goto=END) 로 끝낸다
    # 4) 반려면 REVIEWER_PROMPT 의 verdict, notes, report 자리를 채워 llm.ainvoke 로 고칠 점을 받는다
    #    응답의 .text 를 feedback 으로, 기록용 AIMessage(name="reviewer") 와 함께 Command(goto="supervisor", update=...) 에 review 와 담아 보낸다
    raise NotImplementedError("TODO를 완성하세요")
