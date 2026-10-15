"""도서관 안내 챗봇 코드 가운데 LLM 이 아닌 부분(문맥 만들기, 분기, 인용 확인)입니다.

테스트할 코드라 직접 실행하지 않습니다. 이 파일의 테스트는 함께 따라하기에서 tests/test_followalong.py 에 씁니다.
실행 방법(부록_01_pytest_기초 폴더에서): uv run pytest -v tests/test_followalong.py
"""
import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

ABSTAIN = "제공된 이용 안내에서 확인할 수 없습니다."

answer_prompt = ChatPromptTemplate.from_messages([
    ("system", "도서관 이용 안내 문서로만 답하세요. 문장 끝에 근거 문서 ID 를 [loan-basic] 처럼 붙이세요. "
               "문서에 답이 없으면 '" + ABSTAIN + "'라고만 답하세요."),
    ("human", "질문: {question}\n\n문서:\n{context}"),
])


def format_documents(docs):
    """검색한 문서를 '[근거 ID] 본문' 줄로 이어 프롬프트 문맥을 만듭니다."""
    lines = []
    for doc in docs:
        lines.append(f"[{doc.metadata['source_id']}] {doc.page_content}")
    return "\n\n".join(lines)


def find_citations(reply):
    """답변에 붙은 [근거 ID] 표시를 찾아 ID 목록으로 돌려줍니다."""
    return re.findall(r"\[([a-z0-9-]+)\]", reply)


def answer_question(question, docs, llm):
    """검색한 문서로 답하되, 검색하지 않은 문서를 인용한 답은 안내 문장으로 바꿔 돌려줍니다."""
    # 검색한 문서가 없으면 모델을 부르지 않습니다.
    if len(docs) == 0:
        return ABSTAIN

    chain = answer_prompt | llm | StrOutputParser()
    reply = chain.invoke({"question": question, "context": format_documents(docs)})

    # 검색하지 않은 문서를 인용한 답(모델이 지어낸 근거 ID)은 막습니다.
    # 인용이 없는 답(인사, 되묻기, 안내 문장)은 막을 근거가 없으므로 그대로 돌려줍니다.
    citations = find_citations(reply)
    searched_ids = []
    for doc in docs:
        searched_ids.append(doc.metadata["source_id"])
    for evidence_id in citations:
        if evidence_id not in searched_ids:
            return ABSTAIN

    return reply
