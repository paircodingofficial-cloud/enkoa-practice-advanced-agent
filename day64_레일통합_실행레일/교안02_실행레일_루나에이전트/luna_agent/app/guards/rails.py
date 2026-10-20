"""가드 층: NeMo 판정 객체를 만들고, 앱의 대화 기록을 입력, 출력 레일로 판정한다.

레일의 층 순서와 기준값은 rails/guard 폴더(config.yml, rails.co)가 원본이다. 이 모듈은 그 폴더를 읽기만 한다.
check_input, check_output 은 요청마다 한 번 check_async 를 부르고 작은 dict {status, blocked_by, rule_id, content} 를 돌려준다.
- status: "passed"(통과), "modified"(가림), "blocked"(막음). NeMo 판정 결과의 status 를 그대로 옮긴다
- blocked_by: 막은 레일 흐름 이름(예: jev policy input). NeMo 가 판정 결과의 rail 칸에 알려 준다. 통과하면 빈 문자열
- rule_id: 막은 규칙 id(예: PG2, IN-05, OUT-08). 액션이 정한 값을 거절 문장 끝에서 뗀다. 통과하면 빈 문자열
  판정 액션이 오류를 내면 NeMo 0.23 은 그 레일 이름과 영어 오류 문장으로 막는다(규칙 표시 없음). 이때는 RAIL-ERROR 로 바꾼다
- content: 팬에게 보낼 문장(막았으면 거절 문장, 가렸으면 가린 답변)
NeMo 에 맞지 않는 일은 앱 코드에 둔다. 도구 메시지를 빼고 넘기는 일(to_rail_messages)은 여기서, 검색 결과 검사는 실행 레일(execution.py)이 한다.
"""
import logging

# config 를 nemoguardrails 보다 먼저 불러온다. config 가 NeMo 사용 통계 전송을 끄는 환경 변수를 정한다
from app.core.config import RAILS_DIR

from nemoguardrails import LLMRails, RailsConfig
from nemoguardrails.rails.llm.options import RailStatus, RailType

from app.core.policies import RAIL_ERROR_RULE, reply_for_rule
from app.guards.actions import register_guard_actions

# 입력 레일이 막은 팬 메시지는 대화 기록에서 이 문구로 바꾼다(다음 턴에 공격 문장이 모델에게 다시 가지 않게)
BLOCKED_MESSAGE = "[입력 레일이 막은 메시지]"

# rails.co 의 거절 문장 끝에 붙는 표시. 이 표시 뒤가 막은 규칙 id 다
RULE_MARKER = "막은 규칙: "

# NeMo 판정 객체는 처음 판정할 때 한 번만 만든다(레일 설정 폴더 읽기와 액션 등록)
RAILS = {}


# [보조 함수] 판정 객체 만들기
def build_rails(config_dir=RAILS_DIR) -> LLMRails:
    """설정 폴더로 판정 객체(LLMRails)를 만들고 레일 액션을 등록해 돌려준다."""
    # 폴더의 config.yml 과 rails.co 를 앱을 시작할 때마다 읽는다. 폴더를 고친 뒤 앱을 다시 실행하면 반영된다
    # 판정만 하므로 답변 모델(main) 없이 만든다. 그때 나오는 "No main LLM" 경고는 예상된 경고라 숨긴다
    logging.getLogger("nemoguardrails.rails.llm.llmrails").setLevel(logging.ERROR)
    rails = LLMRails(RailsConfig.from_path(str(config_dir)))
    register_guard_actions(rails)
    return rails


# [보조 함수] 판정 객체
def guard_rails() -> LLMRails:
    """입력, 출력 레일 판정 객체(LLMRails)를 돌려준다. 처음 부를 때만 만든다."""
    # 아직 없으면 만들어 두고, 다음부터는 만들어 둔 것을 쓴다
    if "guard" not in RAILS:
        RAILS["guard"] = build_rails()
    return RAILS["guard"]


# [보조 함수] 레일 판정용 메시지로 바꾸기
def to_rail_messages(messages: list) -> list:
    """대화 기록을 레일 판정용 dict 목록으로 바꾼다. 사람 메시지와 도구 호출이 없는 AI 답변만 담는다."""
    rail_messages = []
    for message in messages:
        # 팬 메시지는 user 로 넣는다
        if message.type == "human":
            rail_messages.append({"role": "user", "content": message.text})

        # 도구 호출 메시지와 도구 결과는 넣지 않는다
        # 섞이면 NeMo 0.23 의 check_async 가 입력 레일을 돌리지 않고 통과시키고, 출력 판정은 내용을 빈 문자열로 바꾼다
        # 도구 호출이 없는 AI 메시지(팬에게 보낸 답)만 assistant 로 넣는다
        if message.type == "ai" and not message.tool_calls:
            rail_messages.append({"role": "assistant", "content": message.text})
    return rail_messages


# [보조 함수] 거절 문장에서 규칙 id 떼기
def split_rule_id(content: str) -> tuple:
    """거절 문장을 (팬에게 보낼 문장, 막은 규칙 id) 로 나눠 돌려준다. 표시가 없으면 규칙 id 는 빈 문자열이다."""
    # 표시가 없음: 우리 흐름이 막은 문장이 아니다(판정 실패 문장 등)
    if RULE_MARKER not in content:
        return content, ""
    # 표시가 있음: 마지막 표시를 기준으로 앞은 문장, 뒤는 규칙 id
    message, rule_id = content.rsplit(RULE_MARKER, 1)
    return message.strip(), rule_id.strip()


# [보조 함수] 판정 결과를 작은 dict 로
def to_verdict(result) -> dict:
    """NeMo 판정 결과(RailsResult)를 {status, blocked_by, rule_id, content} dict 로 바꿔 돌려준다(칸 뜻은 모듈 설명)."""
    # 1. 막힘(blocked): 거절 문장에서 규칙 id 를 떼고, 막은 흐름 이름을 남긴다
    #    어느 흐름이 막았는지는 NeMo 가 result.rail 에 알려 준다(stop 으로 끝난 흐름의 이름)
    if result.status == RailStatus.BLOCKED:
        message, rule_id = split_rule_id(result.content)
        # 규칙 표시 없이 막혔으면 판정 액션이 오류를 낸 것이다(우리 흐름은 모두 표시를 붙여 막는다)
        # NeMo 가 이미 막았으므로(fail-closed) 영어 오류 문장 대신 루나 말투의 안내(REF-10)로 바꾼다
        if rule_id == "":
            rule_id = RAIL_ERROR_RULE
            message = reply_for_rule(RAIL_ERROR_RULE)
        return {"status": "blocked", "blocked_by": result.rail, "rule_id": rule_id, "content": message}

    # 2. 가림(modified): Guardrails AI 층이 개인정보를 가린 답으로 바꿨다. content 가 가린 답이다
    if result.status == RailStatus.MODIFIED:
        return {"status": "modified", "blocked_by": "", "rule_id": "", "content": result.content}

    # 3. 통과(passed): 막은 자리와 규칙 id 는 빈 문자열이다
    return {"status": "passed", "blocked_by": "", "rule_id": "", "content": result.content}


# [보조 함수] 입력 레일 판정
async def check_input(rails: LLMRails, messages: list) -> dict:
    """대화 기록의 마지막 팬 메시지를 입력 레일로 판정한 {status, blocked_by, rule_id, content} dict 를 돌려준다."""
    # 앞선 대화를 함께 넘긴다. NeMo 가 이 대화를 대화 기록(events)으로 바꿔 액션에 넘겨 주므로
    # Jev 입력 층(actions.py 의 jev_policy_input)이 앞선 팬 메시지를 읽어 여러 메시지에 나눠 보낸 공격도 본다
    result = await rails.check_async(to_rail_messages(messages), rail_types=[RailType.INPUT])
    return to_verdict(result)


# [보조 함수] 출력 레일 판정
async def check_output(rails: LLMRails, messages: list, documents_text: str) -> dict:
    """대화 기록의 마지막 답변을 출력 레일로 판정한 {status, blocked_by, rule_id, content} dict 를 돌려준다. documents_text 는 이번 턴의 근거 문서(도구 결과)다."""
    # 근거 문서는 역할(role)이 context 인 메시지로 넘긴다. 빼면 사실 대조 액션이 문서 대신 '$relevant_chunks' 글자를 받는다
    rail_messages = [{"role": "context", "content": {"relevant_chunks": documents_text}}]
    rail_messages.extend(to_rail_messages(messages))
    result = await rails.check_async(rail_messages, rail_types=[RailType.OUTPUT])
    return to_verdict(result)


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.guards.rails
    # 설정 폴더와 메시지 변환만 확인한다. 실제 판정(check_input, check_output)은 분류 모델과 Jev 를 부른다
    from langchain_core.messages import AIMessage, HumanMessage

    print("레일 설정 폴더:", RAILS_DIR, "/ 있음:", RAILS_DIR.exists())
    sample_messages = [
        HumanMessage("내 티켓 좌석 알려 줘"),
        AIMessage("", tool_calls=[{"name": "get_my_tickets", "args": {}, "id": "call_1"}]),
        AIMessage("1층 B구역 7열 12번이에요."),
    ]
    print("레일 판정용 메시지:", to_rail_messages(sample_messages))
    print("거절 문장 나누기:", split_rule_id("그건 도와드릴 수 없어요. 막은 규칙: IN-05"))
    if RAILS_DIR.exists():
        rails = build_rails()
        print("입력 레일 층:", rails.config.rails.input.flows, "/ 출력 레일 층:", rails.config.rails.output.flows)
