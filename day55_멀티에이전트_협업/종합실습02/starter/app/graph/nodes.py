"""그래프 층: 계획, 병렬 조사, 종합, 감독, 작성, 검수, 발행 노드 함수를 모은다."""
import json
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from langgraph.runtime import Runtime
from langgraph.types import Command

from app.core.config import (
    AGENT_CALL_LIMIT,
    MAX_EXTRA_TASKS,
    MAX_ROUNDS,
    MAX_TASKS,
    PASS_SCORE,
    TOOL_CALL_LIMIT,
    llm,
)
from app.core.judge import check_gaps, judge_draft
from app.core.prompts import (
    COVER_PROMPT,
    PLANNER_INPUT,
    PLANNER_PROMPT,
    RESEARCHER_INPUT,
    RESEARCHER_PROMPT,
    REVIEWER_PROMPT,
    REWORK_INPUT,
    REWORK_PROMPT,
    SOURCE_TIPS,
    SYNTHESIZER_INPUT,
    SYNTHESIZER_PROMPT,
    WRITER_INPUT,
)
from app.core.schemas import Brief, Finding, ResearchPlan, ReworkStep
from app.graph.state import Context, ResearchInput, State
from app.tools.cover_image import generate_cover_image


# [보조 함수] JSON 글자 만들기: 프롬프트에 넣을 dict 를 읽기 좋은 JSON 문자열로 펼친다.
def dump_json(data: dict) -> str:
    """dict 를 한글이 깨지지 않는 들여쓴 JSON 문자열로 돌려준다."""
    return json.dumps(data, ensure_ascii=False, indent=1)


# [보조 함수] 출처 모으기: 모든 조사 결과의 출처를 URL 기준으로 한 번씩만 모은다.
def collect_sources(findings: dict) -> list[dict]:
    """모든 조사 결과의 출처를 URL 기준으로 중복 없이 모은 목록을 돌려준다."""
    # URL 을 키로 쓰면 같은 출처가 여러 조사에 나와도 하나만 남는다.
    sources = {}
    for finding in findings.values():
        for source in finding["sources"]:
            sources[source["url"]] = source
    return list(sources.values())


# [노드] 조사 계획
async def planner(state: State) -> dict:
    """새 조사 작업을 plan 뒤에 붙이고 처리한 반려 판정과 지시문을 비운 업데이트를 돌려준다."""
    # 첫 계획은 작업을 넉넉히, 다시 올 때는 부족한 부분만 적게 잡는다.
    if state["findings"]:
        max_tasks = MAX_EXTRA_TASKS
    else:
        max_tasks = MAX_TASKS

    # 이미 조사한 검색어, 추가 조사 항목(gaps), 지시문이 없으면 프롬프트에 "없음"이라고 적는다.
    done = "없음"
    if state["plan"]:
        done = [task["query"] for task in state["plan"]]
    gaps = "없음"
    if state["brief"] and state["brief"]["gaps"]:
        gaps = state["brief"]["gaps"]
    instruction = "없음"
    if state["instruction"]:
        instruction = state["instruction"]

    # 프롬프트를 채워 GPT 구조화 출력으로 조사 계획(ResearchPlan)을 받는다.
    prompt = PLANNER_PROMPT.format(max_tasks=max_tasks)
    message = PLANNER_INPUT.format(
        request=state["request"], report=state["report"], done=done, gaps=gaps, instruction=instruction,
    )
    plan = await llm.with_structured_output(ResearchPlan).ainvoke([("system", prompt), ("user", message)])

    # task_id 는 모델에 맡기지 않고 코드가 이어 붙인다. 번호가 겹치면 앞 조사 결과가 덮이고 새 작업은 끝난 것으로 보여 건너뛰어진다.
    tasks = []
    for task in plan.tasks[:max_tasks]:
        item = task.model_dump()
        item["task_id"] = "t" + str(len(state["plan"]) + len(tasks) + 1)
        tasks.append(item)
    print("planner:", len(tasks), "개 작업", [task["source"] for task in tasks])
    # 반려 판정과 조사 지시문은 이번 계획에 반영했으니 비운다. 지시문을 남기면 writer 가 조사 지시를 글쓰기 지시로 잘못 읽는다.
    # 검수 피드백(feedback)은 writer 가 다시 읽도록 남겨 둔다.
    return {"plan": state["plan"] + tasks, "review": None, "instruction": ""}


# [노드] 조사 작업 하나 실행(Send 로 작업마다 병렬 실행)
async def researcher(state: ResearchInput, runtime: Runtime[Context]) -> dict:
    """조사 작업 하나의 결과를 {"findings": {task_id: 결과}} 로 돌려준다."""
    # Send 가 넘긴 작업 한 건을 꺼낸다.
    task = state["task"]
    print("researcher:", task["task_id"], task["source"], task["query"])
    # TODO: 그 자료원의 도구만 붙인 subagent 를 만들어 실행하고 결과를 돌려주기
    # 1) 실행 컨텍스트의 워커별 도구에서 이 작업의 자료원(task 의 source) 도구만 고른다. 다른 자료원 도구는 이 워커가 모른다
    # 2) RESEARCHER_PROMPT 에 자료원, 자료원별 요령(SOURCE_TIPS), 도구 호출 상한을 채운다
    # 3) create_agent 에 도구, 프롬프트, 출력 형식 Finding, 도구 호출 상한과 모델 호출 상한 미들웨어 두 개를 건다
    # 4) RESEARCHER_INPUT 을 채워 ainvoke 하고, result["structured_response"] 를 model_dump 로 딕셔너리로 바꾼다
    # 5) findings 는 {task_id: 결과} 한 건으로 돌려준다
    raise NotImplementedError("TODO를 완성하세요")


# [노드] 조사 결과 종합
async def synthesizer(state: State) -> dict:
    """조사 결과를 종합한 작성용 브리프를 {"brief": ...} 로 돌려준다."""
    # 조사 결과 전체를 JSON 글자로 펼쳐 넣고 Brief 구조화 출력으로 받는다.
    message = SYNTHESIZER_INPUT.format(
        request=state["request"],
        report=state["report"],
        findings=dump_json(state["findings"]),
    )
    brief = await llm.with_structured_output(Brief).ainvoke([("system", SYNTHESIZER_PROMPT), ("user", message)])
    print("synthesizer:", "추가 조사 항목", len(brief.gaps), "개")
    return {"brief": brief.model_dump()}


# [노드] 다음 단계 결정
async def supervisor(state: State) -> Command[Literal["planner", "writer", "publisher"]]:
    """다음 담당(planner, writer, publisher)으로 가는 Command 를 돌려준다."""
    review = state["review"]
    # writer 는 핸드오프 도구로 실행 도중 빠져나가 자기 반환값이 반영되지 않는다. 그래서 돌려보낸 횟수(round)는 supervisor 가 올린다.
    # 추가 조사 판정은 '더 조사'가 나오기 쉬워서, 보충 조사는 첫 초안 전에 한 번만 보내고 round 에 세지 않는다.
    # 반려 뒤에는 다음 담당과 지시문을 함께 정해야 해서 GPT 구조화 출력을, 보충 조사 여부는 확률 하나면 돼서 Jev 를 쓴다.
    # TODO: 돌려보낸 횟수 상한을 확인하고, 반려가 있으면 GPT 구조화 출력으로 다음 담당과 지시문 정하기
    # 1) state["round"] 가 MAX_ROUNDS 이상이면 더 돌려보내지 않는다. 반려가 있으면 publisher(사람 확인 필요로 저장),
    #    없으면(다시 조사를 마치고 온 경우) writer 로 보낸다
    # 2) review 에 값이 있으면(검수 반려 또는 작성자의 추가 조사 요청) REWORK_INPUT 에 feedback, brief, findings 를 채워
    #    GPT 구조화 출력(ReworkStep)을 받는다. step.next 로 보내며 round 를 1 올리고 step.instruction 을 instruction 에 담는다
    raise NotImplementedError("TODO를 완성하세요")
    # TODO: 반려가 없으면 Jev 로 보충 조사가 필요한지 판단해 planner 또는 writer 로 보내기
    # 1) 첫 초안 전(round == 0)이고 아직 보충 조사를 보내지 않았을 때(gap_filled 가 False)만 check_gaps(state["brief"]) 로 확률을 받는다.
    #    브리프의 gaps(핵심 주장에 필요한데 조사에서 못 찾은 사실) 중 꼭 더 조사해야 할 것이 있을 확률이다
    # 2) 확률이 0.5 이상이면 gap_filled 를 True 로 바꿔 planner 로 보낸다. 보충 조사는 반려가 아니므로 round 는 올리지 않는다
    # 3) 아니면 writer 로 보낸다. 첫 작성도 돌려보낸 것이 아니므로 round 를 올리지 않는다
    raise NotImplementedError("TODO를 완성하세요")


# [노드] 초안 작성: 넘기는 일은 핸드오프 도구가 한다.
async def writer(state: State, runtime: Runtime[Context]) -> Command:
    """작성자 에이전트를 실행하고, 검수 요청 없이 끝났으면 reviewer 로 가는 Command 를 돌려준다."""
    run_dir = runtime.context["run_dir"]
    # 초안 파일 경로는 이번 실행 폴더 안으로 고정한다.
    draft = {"blog": str(run_dir / "blog.md"), "shorts": str(run_dir / "shorts_script.md")}
    # 검수 피드백이 있으면 다시 쓰기, 없으면 첫 초안이다.
    if state["feedback"]:
        feedback = state["feedback"]
        print("writer:", "다시 쓰기")
    else:
        feedback = "없음"
        print("writer:", "첫 초안")
    # supervisor 지시는 다시 쓰기로 왔을 때만 있다. 다시 조사를 거쳐 왔으면 planner 가 비웠다.
    instruction = "없음"
    if state["instruction"]:
        instruction = state["instruction"]
    # 다시 쓰기면 앞 초안을 함께 준다. 안 주면 처음부터 새로 써서 지적받지 않은 곳에 새 문제가 생긴다.
    previous = "없음"
    if (run_dir / "blog.md").exists() and (run_dir / "shorts_script.md").exists():
        blog = (run_dir / "blog.md").read_text(encoding="utf-8")
        shorts = (run_dir / "shorts_script.md").read_text(encoding="utf-8")
        previous = "[블로그 글]\n" + blog + "\n\n[쇼츠 대본]\n" + shorts
    # 브리프와 조사 결과는 JSON 글자로 펼쳐 작성자 입력을 채운다.
    message = WRITER_INPUT.format(
        request=state["request"],
        blog_path=draft["blog"],
        shorts_path=draft["shorts"],
        brief=dump_json(state["brief"]),
        findings=dump_json(state["findings"]),
        feedback=feedback,
        instruction=instruction,
        previous=previous,
    )
    # request_review 가 불리면 이 호출 안에서 바깥 그래프가 reviewer 로 넘어가 아래 줄은 실행되지 않는다.
    await runtime.context["writer"].ainvoke({"messages": message})
    # 작성자가 검수 요청 도구를 부르지 않고 끝나도 그래프가 멈추지 않게, 정해 둔 초안 경로로 reviewer 에 넘긴다.
    print("writer:", "검수 요청 없이 끝나 reviewer 로 넘김")
    return Command(goto="reviewer", update={"draft": draft})


# [노드] 초안 검수
async def reviewer(state: State, runtime: Runtime[Context]) -> Command[Literal["publisher", "supervisor"]]:
    """초안 판정 결과를 싣고 publisher(통과) 또는 supervisor(반려)로 가는 Command 를 돌려준다."""
    run_dir = runtime.context["run_dir"]
    # 작성자가 "blog.md" 처럼 상대 경로를 넘겨도 이번 실행 폴더 기준으로 읽는다. 절대 경로는 그대로 쓰인다.
    blog = (run_dir / state["draft"]["blog"]).read_text(encoding="utf-8")
    shorts = (run_dir / state["draft"]["shorts"]).read_text(encoding="utf-8")
    # TODO: Jev 판정으로 통과를 정하고, 반려면 GPT 피드백을 붙여 supervisor 로 보내기
    # 1) 블로그와 쇼츠를 이어 붙인 글, findings, report 를 judge_draft 에 넘겨
    #    점수 두 개(source_fidelity, reader_value)와 자료와 어긋날 확률(contradiction)을 받는다
    # 2) contradiction 이 0.5 미만이고 두 점수가 모두 PASS_SCORE 이상이면 통과다. 판정을 복사해 passed(통과 여부)를 더한 것을 review 로 둔다
    # 3) 통과면 review 를 실어 publisher 로 가는 Command 를 돌려준다
    # 4) 반려면 REVIEWER_PROMPT 의 verdict, report, findings, blog, shorts 자리를 채워 llm.ainvoke 로 고칠 점을 받는다
    #    응답 메시지의 .text 를 feedback 으로, review 와 함께 supervisor 로 가는 Command 에 담아 돌려준다
    raise NotImplementedError("TODO를 완성하세요")


# [노드] 발행
async def publisher(state: State, runtime: Runtime[Context]) -> dict:
    """통과한 초안은 커버 이미지까지, 미통과 초안은 상태만 sources.json 에 저장하고 빈 업데이트를 돌려준다."""
    run_dir = runtime.context["run_dir"]
    # 돌려보낸 횟수 상한에 닿아 넘어온 반려 초안은 발행하지 않고 사람 확인으로 남긴다. 커버 이미지도 만들지 않는다.
    # 추가 조사 요청 뒤 상한에 닿으면 초안 파일이 없을 수 있어 통과했을 때만 읽는다.
    if state["review"]["passed"]:
        status = "발행"
        blog = (run_dir / state["draft"]["blog"]).read_text(encoding="utf-8")
        first_line = blog.splitlines()[0]
        title = first_line.lstrip("# ")   # 첫 줄 "# 제목" 에서 제목만 쓴다
        await generate_cover_image(COVER_PROMPT.format(title=title), str(run_dir / "cover.png"))
    else:
        status = "라운드 상한 도달: 사람 확인 필요"
    # 발행 여부와 상관없이 상태, 출처, 마지막 판정을 sources.json 에 남긴다.
    record = {"status": status, "sources": collect_sources(state["findings"]), "review": state["review"],
              "feedback": state["feedback"], "round": state["round"]}
    (run_dir / "sources.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print("publisher:", status)
    return {}
