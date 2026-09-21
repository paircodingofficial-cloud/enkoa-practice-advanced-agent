"""교안 02의 질의 변환과 하이브리드 검색을 교안 03에서 재사용합니다.

prepare_retrieval: 전용 수업 컬렉션을 새로 적재하고 검색기·변환 체인을 준비합니다.
retrieve: 선택한 방법 하나만 실행해 (원문 Document 목록, 변환 기록)을 반환합니다.
format_context: 검색된 실제 원문을 답변 문맥으로 만듭니다.

import만으로 API를 호출하지 않습니다. 모델과 키는 노트북에서 설정합니다.
"""
from kiwipiepy import Kiwi
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
from langchain_classic.chains.query_constructor.schema import AttributeInfo
from langchain_classic.retrievers.self_query.base import SelfQueryRetriever
from langchain_classic.retrievers.multi_query import MultiQueryRetriever
from langchain_community.query_constructors.chroma import ChromaTranslator
from langchain_chroma import Chroma
from pydantic import BaseModel, Field

def make_documents(records):
    """원문 기록의 본문·출처와 검색 조건을 LangChain Document로 바꿉니다."""
    # id는 저장소가, metadata의 source_id는 RRF가 원문을 구별할 때 읽습니다.
    # 두 위치에 같은 원문 ID를 사용하고 출처·필터 메타데이터를 담습니다.
    return [Document(
        id=record["doc_id"],
        page_content=record["text"],
        metadata={"source_id": record["doc_id"], "title": record["title"],
                  "url": record["url"], "source": record["source"], **record["metadata"]},
    ) for record in records]

# 분석기는 한 번 준비해 문서와 질문 양쪽에 같은 방식으로 적용합니다.
kiwi = Kiwi()


def kiwi_tokenize(text):
    """명사·외국어·숫자를 소문자 토큰 목록으로 돌려줍니다."""
    # PDF 표기 통일: 재택･원격근무 -> 재택·원격근무
    text = text.replace("･", "·")
    # N 계열은 명사, SL은 외국어, SN은 숫자입니다. 조사는 제외합니다.
    # lower는 영문 대소문자를 통일합니다. 기호가 중요한 제품 코드는 별도로 살펴봅니다.
    return [token.form.lower() for token in kiwi.tokenize(text)
            if token.tag.startswith("N") or token.tag in {"SL", "SN"}]

def search_with_filter(query, where, bm25, vector_store, hybrid, k):
    """기존 BM25를 재사용하고 같은 조건의 Dense 결과와 합칩니다."""
    # 두 검색에 적용할 조건 일치 문서 ID를 Chroma에서 조회합니다.
    matched = vector_store.get(where=where, include=["metadatas"])
    allowed_ids = {item["source_id"] for item in matched["metadatas"]}
    if not allowed_ids:
        return []
    if not query.strip():
        candidates = [doc for doc in bm25.docs if doc.metadata["source_id"] in allowed_ids]
        return sorted(candidates, key=lambda doc: doc.metadata["source_id"])[:k]

    # BM25 점수를 계산합니다.
    scores = bm25.vectorizer.get_scores(bm25.preprocess_func(query))

    # 조건에 맞는 문서와 점수만 남깁니다.
    scored_candidates = [
        (doc, score) for doc, score in zip(bm25.docs, scores)
        if doc.metadata["source_id"] in allowed_ids
    ]

    # 조건에 맞는 문서를 BM25 점수 내림차순으로 정렬해 상위 k개를 선택합니다.
    scored_candidates.sort(key=lambda item: item[1], reverse=True)
    bm25_results = [doc for doc, score in scored_candidates[:k]]

    # Dense도 같은 조건을 적용해 실제 벡터 DB에서 검색합니다.
    dense_results = vector_store.similarity_search(query, k=k, filter=where)

    # 문서별 가중 RRF 점수를 합산해 내림차순으로 정렬하고 상위 k개를 반환합니다.
    return hybrid.weighted_reciprocal_rank([bm25_results, dense_results])[:k]

# 여러 질문이 같은 원문을 찾아도 답변 문맥에는 한 번만 넣습니다.
def unique_documents(documents):
    """원문 ID를 기준으로 첫 등장 순서를 유지하며 중복을 제거합니다."""
    by_id = {}
    for doc in documents:
        source_id = doc.metadata["source_id"]
        if source_id not in by_id:
            by_id[source_id] = doc
    return list(by_id.values())

# 본문과 조건 메타데이터를 함께 줘 연도·분류·쪽수도 답변에서 확인할 수 있게 합니다.
def format_context(documents):
    """실제 검색 문서의 본문·메타데이터·출처를 답변 문맥으로 만듭니다."""
    return "\n\n".join(
        f"[{doc.metadata['source_id']}] {doc.metadata['title']}\n"
        f"메타데이터: {doc.metadata}\n본문: {doc.page_content}"
        for doc in documents
    )


class SubQuestions(BaseModel):
    """원질문을 나누어 검색할 하위 질문 목록입니다."""
    questions: list[str] = Field(
        description=(
            "원질문의 서로 다른 정보 요구를 하나씩 묻는 질문 2~3개. "
            "각 질문만으로 검색할 수 있게 대상과 조건을 포함하고, "
            "원질문에 없는 요구를 추가하지 않으며 같은 언어로 작성."
        ),
        min_length=2, max_length=3,
    )


def prepare_query_transforms(llm, vector_store, hybrid, k):
    """교안 02의 다섯 변환 체인을 만들어 반환합니다. 아직 GPT를 호출하지 않습니다."""
    # 검색어와 조건을 추출하는 규칙입니다.
    query_schema_prompt = PromptTemplate.from_template(
        "마지막 User Query를 검색어와 메타데이터 조건으로 나누세요. "
        "query에는 본문에서 찾을 핵심 주제를, filter에는 명시된 조건을 넣습니다. "
        "조건이 없을 때만 filter를 NO_FILTER로 적으세요. "
        "filter는 비교 연산자({allowed_comparators})와 논리 연산자({allowed_operators})로 표현합니다. "
        "Data Source에 정의된 필드만 사용하며, 숫자는 문자열로 바꾸지 마세요."
    )

    # 검색 조건으로 사용할 메타데이터 필드를 알려 줍니다.
    metadata_field_info = [
        AttributeInfo(name="category", description="장서 분류. 컴퓨터, 수학, 과학, 역사, 문학 중 하나", type="string"),
        AttributeInfo(name="year", description="가상 장서의 출판 연도", type="integer"),
    ]

    self_query = SelfQueryRetriever.from_llm(
        llm=llm, vectorstore=vector_store, document_contents="수업용 가상 도서 목록의 제목과 소개문",
        metadata_field_info=metadata_field_info,
        chain_kwargs={"schema_prompt": query_schema_prompt},
        structured_query_translator=ChromaTranslator(), search_kwargs={"k": k},
    )

    # 가상문서는 검색에만 쓰고 최종 답변은 실제 원문으로 작성합니다.
    hyde_prompt = ChatPromptTemplate.from_messages([
        ("system", "질문에 답할 내용이 담긴 가상의 원문을 3문장 이내로 작성하세요. "
                   "각 요구에 필요한 핵심 개념을 해당 분야의 표준 용어로 명시하고 설명하세요. "
                   "질문을 다시 쓰거나 관련 주제를 추가하지 마세요. "
                   "도서 검색 질문에는 해당 내용을 가르치는 책의 소개문을 쓰되 책 제목·저자·출판사는 만들지 마세요. "
                   "확인되지 않은 구체적인 수치나 규정을 지어내지 마세요. "
                   "강조 기호·요청문·검색어 목록 없이 한글 원문만 출력하세요."),
        ("human", "{question}"),
    ])
    hyde_chain = hyde_prompt | llm | StrOutputParser()

    # from_llm의 기본 줄 단위 파서가 읽을 수 있게 번호 없이 한 줄에 하나씩 받습니다.
    multi_prompt = ChatPromptTemplate.from_template(
        "질문과 같은 의미를 유지하는 검색 질문을 서로 다른 표현으로 정확히 3개 작성하세요. "
        "일상 표현을 관련 분야의 표준 용어로 바꾼 질문도 포함하세요. "
        "원문의 정보 요구·고유명사·조건을 유지하세요. 질문의 언어를 유지하세요. "
        "설명·번호·빈 줄 없이 한 줄에 질문 하나만 출력하세요.\n질문: {question}"
    )

    multi_query = MultiQueryRetriever.from_llm(
        retriever=hybrid, llm=llm, prompt=multi_prompt, include_original=True,
    )

    # 구체적 사례를 배경 원리로 바꾸는 예시를 함께 보여 줍니다.
    stepback_prompt = ChatPromptTemplate.from_messages([
        ("system", "원질문의 구체적인 대상과 작업을 제거하고, 그 배경이 되는 기초 개념 자체를 묻는 질문 하나를 작성하세요. "
                   "핵심 개념의 이름을 명시하세요. "
                   "원래 대상의 처리 방법을 다른 말로 다시 묻지 마세요. "
                   "도서 추천 요청이나 답변 없이 한글 질문만 출력하세요."),
        ("human", "자동차의 이동 거리를 시간별로 기록했을 때 특정 순간의 속도는 어떻게 구하나요?"),
        ("ai", "도함수와 순간 변화율은 어떤 관계이며, 함수의 변화를 어떻게 나타내나요?"),
        ("human", "{question}"),
    ])
    stepback_chain = stepback_prompt | llm | StrOutputParser()

    # 스키마는 목록 모양을 제어합니다. 질문이 원의도를 보존했는지는 사람이 읽습니다.
    decompose_prompt = ChatPromptTemplate.from_messages([
        ("system", "원질문의 서로 다른 정보 요구를 하나씩 묻는 질문 2~3개로 나누세요. "
                   "각 질문만으로 검색할 수 있게 대상과 조건을 포함하세요. 원질문에 없는 요구를 추가하지 말고 같은 언어로 작성하세요."),
        ("human", "{question}"),
    ])
    decompose_chain = decompose_prompt | llm.with_structured_output(
        SubQuestions, method="json_schema",
    )
    return {
        "self_query": self_query,
        "hyde": hyde_chain,
        "multi_query": multi_query,
        "step_back": stepback_chain,
        "decomposition": decompose_chain,
    }


def prepare_retrieval(records, llm, embedding_model, k=3,
                      collection_name="day47_jev_router_books"):
    """원문을 임베딩해 적재하고 검색기·변환 체인을 딕셔너리로 반환합니다."""
    documents = make_documents(records)
    # 같은 이름의 수업용 메모리 컬렉션만 다시 만들고 실제 원문을 임베딩합니다.
    vector_store = Chroma(collection_name=collection_name, embedding_function=embedding_model)
    vector_store.reset_collection()
    vector_store.add_documents(documents)
    bm25 = BM25Retriever.from_documents(documents, preprocess_func=kiwi_tokenize, k=k)
    dense = vector_store.as_retriever(search_kwargs={"k": k})
    hybrid = EnsembleRetriever(
        retrievers=[bm25, dense], weights=[0.5, 0.5], c=60, id_key="source_id",
    )
    transforms = prepare_query_transforms(llm, vector_store, hybrid, k)
    return {
        "vector_store": vector_store, "bm25": bm25, "dense": dense, "hybrid": hybrid,
        "transforms": transforms, "k": k, "document_count": len(documents),
    }


def retrieve(question, method, retrieval):
    """선택된 교안 02 방법만 실제 실행하고 원문과 변환 기록을 반환합니다."""
    vector_store = retrieval["vector_store"]
    bm25, dense, hybrid = retrieval["bm25"], retrieval["dense"], retrieval["hybrid"]
    k = retrieval["k"]
    transforms = retrieval["transforms"]
    self_query = transforms["self_query"]
    hyde_chain = transforms["hyde"]
    multi_query = transforms["multi_query"]
    stepback_chain = transforms["step_back"]
    decompose_chain = transforms["decomposition"]
    if method == "self_query":
        parsed = self_query.query_constructor.invoke({"query": question})
        query_text, search_kwargs = ChromaTranslator().visit_structured_query(parsed)
        where = search_kwargs.get("filter")
        found = search_with_filter(query_text, where, bm25, vector_store, hybrid, k=k)
        trace = {"queries": [query_text], "filter": where}
    elif method == "hyde":
        hypothetical_text = hyde_chain.invoke({"question": question})
        bm25_results = bm25.invoke(question)
        dense_results = dense.invoke(hypothetical_text)
        found = hybrid.weighted_reciprocal_rank([bm25_results, dense_results])[:k]
        trace = {"bm25_query": question, "hypothetical_text": hypothetical_text}
    elif method == "multi_query":
        generated_queries = multi_query.llm_chain.invoke({"question": question})
        queries = [question] + generated_queries
        groups = hybrid.batch(queries)
        found = unique_documents([doc for group in groups for doc in group])
        trace = {"queries": queries}
    elif method == "step_back":
        background_question = stepback_chain.invoke({"question": question})
        queries = [question, background_question]
        groups = hybrid.batch(queries)
        found = unique_documents([doc for group in groups for doc in group[:k]])
        trace = {"queries": queries}
    elif method == "decomposition":
        sub_questions = decompose_chain.invoke({"question": question})
        groups = hybrid.batch(sub_questions.questions)
        found = unique_documents([doc for group in groups for doc in group[:k]])
        trace = {"queries": sub_questions.questions}
    else:
        raise ValueError("실행할 질의 변환 방법이 아닙니다.")
    return found, trace
