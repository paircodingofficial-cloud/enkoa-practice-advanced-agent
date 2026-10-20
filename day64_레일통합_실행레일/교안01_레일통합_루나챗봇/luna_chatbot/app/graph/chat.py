"""그래프 층: 실행 값(ChatContext)을 만들고, 대화 ID 하나에 팬 메시지 한 턴을 보내고, 턴 결과를 요약한다.

CLI(main.py), 평가(evaluate.py), 화면(ui/chat_app.py)이 모두 이 세 함수로 그래프를 쓴다.
"""
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.core.policies import PERSONA
from app.core.prompts import BASE_TIME_TEXT
from app.core.schemas import ChatContext
from app.guards.rails import build_rails
from app.tools.retriever import get_vector_store


# [보조 함수] 실행 값 만들기
def build_chat_context(fan_id: str | None = None) -> ChatContext:
    """판정 객체와 검색기를 만들어 로그인한 팬 id 와 함께 묶어 돌려준다."""
    # 만들 때는 API 를 부르지 않는다. 검색 저장소는 준비 단계(uv run -m app.tools.retriever --build)에서 만들어 둔다
    # 검색기는 질문 하나에 절 retriever_k 개를 돌려준다
    return ChatContext(
        rails=build_rails(),
        retriever=get_vector_store().as_retriever(search_kwargs={"k": settings.retriever_k}),
        fan_id=fan_id,
    )


# [보조 함수] 한 턴 보내기
async def send_message(app, thread_id: str, text: str, context: ChatContext) -> dict:
    """대화 ID 하나에 팬 메시지 하나를 보내고, 그 턴이 끝났을 때의 State 를 돌려준다."""
    # 같은 thread_id 로 보내면 체크포인터가 앞 턴의 messages 를 꺼내 이 메시지 앞에 붙여 준다
    config = {"configurable": {"thread_id": thread_id}}
    return await app.ainvoke({"messages": [HumanMessage(content=text)]}, config, context=context)


# [보조 함수] 턴 결과 요약
def summarize_turn(state: dict) -> dict:
    """한 턴이 끝난 State 에서 화면, CLI, 평가가 쓰는 값만 꺼낸 턴 요약 dict 를 돌려준다.

    answer(팬에게 간 마지막 메시지), route, blocked_by, rule_id, input_status, output_status(통과, 가림, 막음, 판정 안 했으면 빈 문자열),
    search_query, retrieved_ids(검색 레일이 남긴 절 id), removed_doc_ids, contexts(평가에 넘길 근거 글 목록), cards
    """
    # 검색 레일이 남긴 문서의 절 id 와 본문을 따로 모은다
    retrieved_ids = []
    contexts = []
    for doc in state["retrieved_docs"]:
        retrieved_ids.append(doc.metadata["source_id"])
        contexts.append(doc.page_content)

    # DB 를 조회한 턴이면: DB 에서 조회한 정보도 답의 근거라 평가(Faithfulness)에 함께 넘긴다
    # 조회한 정보로 답하는 질문(취소 마감, 환불 기한)은 '지금'에 기대어 답하므로 답변 모델이 받은 기준 시각도 앞에 넣는다
    if state["lookup_text"] != "":
        contexts.insert(0, state["lookup_text"])
        contexts.insert(0, BASE_TIME_TEXT)

    # 답변 모델과 사실 대조가 받은 기본 사실도 근거라 함께 넘긴다. 근거가 없는 턴(정해 둔 답, 일상 대화)은 그대로 비워 둔다
    if len(contexts) > 0:
        contexts.append(PERSONA["facts"])

    return {
        "answer": state["messages"][-1].text,
        "route": state["route"],
        "blocked_by": state["blocked_by"],
        "rule_id": state["rule_id"],
        "input_status": state["input_check"].get("status", ""),
        "output_status": state["output_check"].get("status", ""),
        "search_query": state["search_query"],
        "retrieved_ids": retrieved_ids,
        "removed_doc_ids": state["removed_doc_ids"],
        "contexts": contexts,
        "cards": state["cards"],
    }


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.chat
    # 판정 객체와 검색기는 만들기만 한다(API 를 부르지 않는다). 검색 저장소는 준비 단계에서 만들어 둔다
    from langchain_core.messages import AIMessage

    from app.graph.state import empty_turn

    sample = empty_turn()
    sample["messages"] = [HumanMessage("안녕"), AIMessage("안녕하세요, 루미!")]
    sample["route"] = "chitchat"
    print("턴 요약:", summarize_turn(sample))
    context = build_chat_context("F0001")
    print("실행 값:", type(context.rails).__name__, context.fan_id)
