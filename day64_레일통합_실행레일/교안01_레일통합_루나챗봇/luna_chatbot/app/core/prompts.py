"""프롬프트 층: 이 앱이 모델에게 보내는 글을 모은다.

정책 담당이 고치는 글(시스템 프롬프트, 기본 사실, Jev 판정 정책)은 persona.yaml 에 완성된 글로 있고, 여기서는 그대로 읽는다.
이 챗봇에만 쓰는 규칙(답변 규칙, 일상 대화 규칙, 다시 만들 때 고칠 점, 검색어 다시 쓰기, 경로 후보)은 여기 상수로 적는다.
위기 신호 후보의 설명은 persona.yaml 의 crisis_signals 표에서 읽는다.
입력, 출력 레일의 Jev 판정 질문 문장(규칙 고르기, 사실 대조)은 guards/judges.py 에 있다.
"""
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.core.config import BASE_DATETIME
from app.core.policies import PERSONA

# [프롬프트] 루나 시스템 프롬프트: persona.yaml 의 글에서 {facts} 자리에 기본 사실 블록을 끼운다
SYSTEM_PROMPT = PERSONA["system_prompt"].format(facts=PERSONA["facts"])

# [프롬프트] Jev 입력, 출력 레일 판정 정책(persona.yaml 의 글 그대로)
INPUT_POLICY = PERSONA["input_policy"]
OUTPUT_POLICY = PERSONA["output_policy"]

# [프롬프트] 답변 규칙: 앞 대화를 그대로 넘기면 모델이 앞 질문에 다시 답하므로 뜻 파악에만 쓰게 한다
ANSWER_RULES = """[답변 규칙]
- 앞 대화는 마지막 질문의 뜻을 파악하는 데만 쓴다. 이미 답한 내용은 다시 말하지 않는다.
- 아래 기본 사실, 검색 문서, 조회한 내 정보에 있는 내용만 근거로 마지막 질문에 답한다.
- 마지막 질문에 답할 내용이 문서에 없으면 확인할 수 없다고 말하고, 지어내지 않는다."""

# [프롬프트] 일상 대화 규칙: 답변 규칙을 붙이면 안부에도 '문서에 없어 확인할 수 없다'고 답하므로 따로 둔다
SMALL_TALK_RULES = """[일상 대화 규칙]
- CHAT-01: 응원, 감사, 칭찬, 안부에는 루나로서 두 문장 안으로 다정하게 답합니다.
- CHAT-02: 일정, 시각, 가격, 혜택은 기본 사실에 적힌 것만 말합니다. 루나의 하루 일과, 새 소식, 새 일정은 지어내지 않습니다.
- CHAT-03: 공연, 굿즈, 팬클럽 규정이나 내 예매가 궁금해 보이면 그 내용을 물어봐 달라고 안내합니다."""

# 근거 맨 앞에 두는 '지금'. 답변 모델, 출력 레일 사실 대조, 평가가 같은 줄을 받아야 날짜를 따지는 답이 어긋나지 않는다
BASE_TIME_TEXT = f"[기준 시각] 지금은 {BASE_DATETIME} 입니다."

# [프롬프트] 답변: 고정 글은 partial 로 미리 채운다(값으로 넣은 글 속 중괄호는 변수로 읽히지 않는다)
ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}\n\n{answer_rules}\n\n[검색 문서]\n{context}"),
    MessagesPlaceholder("messages"),
]).partial(system_prompt=SYSTEM_PROMPT, answer_rules=ANSWER_RULES)

# [프롬프트] 일상 대화: 검색 문서 없이 시스템 프롬프트와 일상 대화 규칙만 준다
SMALL_TALK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "{system_prompt}\n\n{small_talk_rules}"),
    MessagesPlaceholder("messages"),
]).partial(system_prompt=SYSTEM_PROMPT, small_talk_rules=SMALL_TALK_RULES)

# [프롬프트] 다시 만들 규칙과 고칠 점: 출력 레일이 이 규칙으로 막으면 답을 한 번만 다시 만든다(교안 02 와 같은 뜻)
# 근거에 없는 내용(OUT-05)과 규정에 없는 예외 약속(OUT-09)은 답변 모델의 실수일 때가 많아, 고칠 점을 주고 다시 쓰면 대개 고쳐진다
# 나머지 출력 규칙(비하, 내부 정보, 다른 팬 정보, 사생, 문서 속 지시, 캐릭터 깨기, 외부 링크)은 위험한 맥락일 수 있어 다시 만들지 않고 바로 거절한다
# 고칠 점은 다시 만드는 호출에만 넣고 대화 기록에는 저장하지 않는다
RETRY_RULES = {
    "OUT-05": "[고칠 점] 방금 쓴 답에 근거에 없는 사실이 섞여 보내지 못했습니다. 근거에 적힌 사실만으로 다시 답하고, 근거에 없으면 확인할 수 없다고 말하세요.",
    "OUT-09": "[고칠 점] 방금 쓴 답이 규정에 없는 예외를 약속해 보내지 못했습니다. 규정에 적힌 대로만 안내하고, 예외는 약속하지 마세요.",
}

# [프롬프트] 검색어 다시 쓰기: 이미 답한 질문까지 넣으면 같은 문서만 다시 찾으므로 마지막 질문이 묻는 것만 담게 한다
REWRITE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "앞 대화를 참고해 팬의 마지막 질문을 앞 대화 없이도 뜻이 통하는 검색어 한 문장으로 바꾸세요. "
               "마지막 질문이 묻는 것만 담고, 앞에서 이미 답한 질문은 넣지 마세요. "
               "검색어만 쓰고, 대화에 없는 사실은 넣지 마세요."),
    ("human", "앞 대화:\n{history}\n\n마지막 질문: {question}"),
])

# [프롬프트] 경로 후보(경로 이름: 한 줄 설명). 라우터 노드가 Jev 에게 이 가운데 하나만 고르게 한다
# 이름은 State 의 route 값이고 graph/edges.py 의 ROUTE_NODES 와 같아야 한다. 경로를 더하면 두 곳을 함께 고친다
ROUTES = {
    "chitchat": "인사, 응원, 감사, 칭찬, 안부처럼 묻는 것이 없는 일상 대화",
    "venue": "공연장 위치와 찾아가는 길",
    "my_ticket": "로그인한 팬 본인의 예매 내역, 좌석, 상태만 묻는 질문(규정이나 날짜는 묻지 않음)",
    "my_order": "로그인한 팬 본인의 굿즈 주문, 배송 상태만 묻는 질문(규정이나 날짜는 묻지 않음)",
    "my_ticket_rule": "'제 티켓', '내 예매'처럼 본인 예매를 가리키면서 규정, 수수료, 마감, 일정도 함께 묻는 질문",
    "my_order_rule": "'제 주문', '내 굿즈'처럼 본인 주문을 가리키면서 규정, 수수료, 마감, 일정도 함께 묻는 질문",
    "out_of_scope": "루나 서비스와 관계없는 질문(영화 추천, 숙제, 주식, 다른 회사 서비스)",
    "rag": "공지, 규정, 굿즈 정보, 공연장 안전과 응급 상황, 신고 방법, 회원 정보 수정 같은 이용 안내, "
           "'티켓을 취소하면'처럼 누구의 것인지 말하지 않은 일반 규정 질문, 루나의 노래와 활동 소식, 그리고 애매하면 이 경로",
}

# [프롬프트] 경로 고르기 질문: 문장 일부가 아니라 마지막 메시지 전체의 뜻으로 고르게 한다
ROUTE_INSTRUCTION = (
    "팬의 마지막 메시지에 답하려면 어느 경로로 가야 하는지 아래 경로 가운데 하나만 고르세요. "
    "마지막 메시지가 실제로 묻는 것으로 고르고, 인사나 감탄이 섞여 있어도 묻는 것이 있으면 그것으로 고릅니다. "
    "앞 대화는 '거기', '그거'처럼 가리키는 말이 무엇인지 알아내는 데만 씁니다. "
    "my_ 로 시작하는 경로는 '제', '내', 티켓 번호, 주문 번호처럼 팬 본인의 예매나 주문을 직접 가리킬 때만 고릅니다. "
    "위험해 보이는 낱말이 있어도 루나 서비스의 이용 안내를 묻는 질문이면 업무 밖이 아닙니다."
)

# [프롬프트] 위기 신호 후보: 입력 레일이 공격을 막은 메시지에도 위기 안내(CRI-01, CRI-02)는 빠지면 안 된다
# 설명은 persona.yaml 의 crisis_signals 표(시스템 프롬프트 [위기 대응] 줄과 같은 글)를 읽고, '없음' 후보만 더한다
# 거절 노드(refuse)가 Jev 에게 하나만 고르게 한다
NO_CRISIS = "none"
CRISIS_SIGNALS = dict(PERSONA["crisis_signals"])
CRISIS_SIGNALS[NO_CRISIS] = "위기 신호가 없다"
CRISIS_INSTRUCTION = "팬 메시지에 아래 위기 신호가 있는지 하나만 고르세요. 장난처럼 말했거나 다른 요청과 섞여 있어도 위기 신호로 봅니다."


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.core.prompts
    # 글과 프롬프트 변수만 본다(API 를 부르지 않는다)
    print("시스템 프롬프트 글자 수:", len(SYSTEM_PROMPT))
    print(SYSTEM_PROMPT[:300])
    print("입력 정책 앞부분:", INPUT_POLICY[:120])
    print("출력 정책 앞부분:", OUTPUT_POLICY[:80])
    print(BASE_TIME_TEXT)
    print("답변 프롬프트 변수:", ANSWER_PROMPT.input_variables)
    print("일상 대화 프롬프트 변수:", SMALL_TALK_PROMPT.input_variables)
    print("다시 쓰기 프롬프트 변수:", REWRITE_PROMPT.input_variables)
    print("경로 후보:", list(ROUTES))
    print("위기 신호 후보:", list(CRISIS_SIGNALS))
    print("다시 만들 규칙:", list(RETRY_RULES))
