"""도서관 안내 RAG 앱. 변경 요청(PR)은 보통 이 파일의 설정이나 프롬프트를 고칩니다."""
import os
from pathlib import Path

import mlflow
from dotenv import find_dotenv, load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
load_dotenv(find_dotenv(usecwd=True))

# 앱 설정: 이 값을 바꾸는 변경 요청이 품질을 떨어뜨리면 CI가 막습니다.
TOP_K = 3
PROMPT_VERSION = "v1"
MODEL_NAME = os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1")

llm = ChatOpenAI(model=MODEL_NAME, use_responses_api=True)
embedding_model = OpenAIEmbeddings(model="text-embedding-3-large", dimensions=768,
                                   check_embedding_ctx_length=False)
vector_store = Chroma(collection_name="library_docs", embedding_function=embedding_model,
                      persist_directory=str(ROOT / "data" / "chroma"))


class Citation(BaseModel):
    evidence_id: str = Field(description="근거 ID를 넣습니다. 제공된 ID를 철자 그대로 씁니다")
    quote: str = Field(description="그 근거 원문에서 글자 그대로 복사한 구절을 넣습니다. 고치거나 요약하지 않습니다")


class Segment(BaseModel):
    text: str = Field(description="답변의 한 부분(보통 문장 하나)을 넣습니다. segments 의 text 를 순서대로 이으면 사용자에게 보여 줄 답변이 됩니다")
    citations: list[Citation] = Field(description="이 부분을 뒷받침하는 인용 목록입니다. 문서에서 가져온 사실이 아니면(연결 문장, 확인할 수 없다는 안내 등) 빈 목록입니다")


class CitedAnswer(BaseModel):
    segments: list[Segment] = Field(description="답변을 순서대로 나눈 부분 목록입니다")


cited_prompt = ChatPromptTemplate.from_messages([
    ("system", "도서관 이용 안내 문서로만 답하세요. 답변을 부분(segments)으로 나눠 쓰고, 문서에서 가져온 사실을 쓴 부분마다 근거 ID와 "
               "그 문서에서 글자 그대로 복사한 구절을 인용하세요. 구절을 바꿔 쓰거나 요약하지 마세요. 조건과 예외가 있으면 함께 쓰세요. "
               "문서에 답이 없으면 '제공된 이용 안내에서 확인할 수 없습니다.'라는 부분 하나만 인용 없이 쓰세요."),
    ("human", "질문: {question}\n\n문서:\n{context}"),
])
cited_chain = cited_prompt | llm.with_structured_output(CitedAnswer)


@mlflow.trace(span_type="RETRIEVER")
def search_documents(search_query, top_k=TOP_K):
    """질문과 가까운 안내 문서 top_k 개를 Document 목록으로 반환합니다."""
    return vector_store.similarity_search(search_query, k=top_k)


def format_documents(docs):
    """검색 문서를 [근거 ID] 제목과 본문 형식으로 이어 붙입니다."""
    parts = []
    for doc in docs:
        parts.append(f"[{doc.metadata['source_id']}] {doc.metadata['title']}\n{doc.page_content}")
    return "\n\n".join(parts)


@mlflow.trace
def answer_with_citations(question, top_k=TOP_K):
    docs = search_documents(question, top_k)
    result = cited_chain.invoke({"question": question, "context": format_documents(docs)})

    # 구조화 출력 객체를 dict 로 바꿉니다. 채점 함수는 이 dict 를 outputs 로 읽습니다.
    output = result.model_dump()

    # 부분을 순서대로 이어 사용자에게 보여 줄 답변을 만듭니다.
    texts = []
    for segment in output["segments"]:
        texts.append(segment["text"])
    output["answer"] = " ".join(texts)

    # 검색한 근거 ID도 넣어야 "검색하지 않은 문서를 인용했는지" 검사할 수 있습니다.
    output["searched_ids"] = []
    for doc in docs:
        output["searched_ids"].append(doc.metadata["source_id"])
    return output
