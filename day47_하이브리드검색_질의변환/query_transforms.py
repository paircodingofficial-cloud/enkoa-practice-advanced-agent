"""교안 02의 질의 변환과 하이브리드 검색을 교안 03에서 재사용합니다.

사용 순서:
    1. prepare_retrieval로 원문을 적재하고 검색기와 질의 변환 체인을 준비합니다.
    2. retrieve에 원질문과 선택한 방법을 전달해 found와 trace를 받습니다.
    3. format_context(found)를 원질문과 함께 답변 체인에 전달합니다.

주요 데이터:
    retrieval: 여러 질문에서 재사용할 검색기·질의 변환 체인을 담은 dict입니다.
    found: 검색된 원문 Document 객체의 list이며, 최종 답변의 근거로 씁니다.
    trace: 검색에 사용한 질문·필터·가상 소개문을 담은 dict입니다.
        교안에서 검색 과정을 확인하기 위해 만든 기록이며, 답변 근거로 쓰지 않습니다.

모델과 API 키는 노트북에서 설정합니다. import는 API를 호출하지 않습니다.
prepare_retrieval은 문서 임베딩을, retrieve는 질의 변환과 검색 요청을 수행합니다.
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
    """원문 기록을 검색에 사용할 LangChain Document 목록으로 바꿉니다.
    
    매개변수:
        records (list[dict]): doc_id, text, title, url, source, metadata가 있는 기록 목록.
            metadata에는 category·year처럼 검색 조건으로 사용할 속성을 담습니다.
    
    반환값:
        list[Document]: text를 page_content로, doc_id를 id와 metadata의 source_id로
            넣은 목록입니다. 제목·출처와 원래 metadata의 속성도 함께 보관합니다.
    
    원문을 객체로 변환하는 단계이며 임베딩이나 검색은 수행하지 않습니다.
    """
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
    """BM25가 문서와 질문을 비교할 때 사용할 단어 목록을 만듭니다.
    
    매개변수:
        text (str): 분석할 문서 본문 또는 검색 질문.
    
    반환값:
        list[str]: Kiwi가 분석한 명사(N 계열)·외국어(SL)·숫자(SN) 토큰입니다.
            영문은 소문자로 바꾸고 원문에 등장한 순서와 반복을 유지합니다.
    
    문서 적재와 질문 검색에 같은 전처리를 적용합니다. 조사는 검색어에서 제외합니다.
    """
    # PDF 표기 통일: 재택･원격근무 -> 재택·원격근무
    text = text.replace("･", "·")
    # N 계열은 명사, SL은 외국어, SN은 숫자입니다. 조사는 제외합니다.
    # lower는 영문 대소문자를 통일합니다. 기호가 중요한 제품 코드는 별도로 살펴봅니다.
    return [token.form.lower() for token in kiwi.tokenize(text)
            if token.tag.startswith("N") or token.tag in {"SL", "SN"}]

def search_with_filter(query, where, bm25, vector_store, hybrid, k):
    """같은 메타데이터 조건을 적용한 BM25·Dense 결과를 RRF로 합칩니다.
    
    매개변수:
        query (str): 본문에서 찾을 검색어.
        where (dict | None): Chroma 형식의 메타데이터 조건. None이면 조건이 없습니다.
        bm25 (BM25Retriever): 적재된 문서와 단어별 점수를 가진 BM25 검색기.
        vector_store (Chroma): 동일한 문서의 본문·메타데이터·벡터를 저장한 저장소.
        hybrid (EnsembleRetriever): 두 검색 순위를 합칠 가중치와 RRF 설정을 가진 검색기.
        k (int): 각 검색에서 선택할 문서 수이자 최종 반환 개수의 상한.
    
    반환값:
        list[Document]: 조건에 맞는 문서를 가중 RRF 점수 내림차순으로 최대 k개 반환합니다.
            조건에 맞는 원문이 없으면 빈 리스트를 반환합니다.
    
    처리 과정:
        조건을 만족하는 원문 ID를 조회한 뒤 BM25와 Dense에 같은 조건을 적용합니다.
        query가 비어 있으면 유사도 검색 없이 조건에 맞는 원문을 source_id 순으로
        최대 k개 반환합니다. query가 있으면 Dense 검색에서 질문 임베딩을 요청합니다.
    """
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
    """source_id가 같은 원문을 하나만 남기고 첫 등장 순서를 유지합니다.
    
    매개변수:
        documents (list[Document]): 여러 질문의 검색 결과를 이어 붙인 원문 목록.
            각 문서의 metadata에 source_id가 있어야 합니다.
    
    반환값:
        list[Document]: source_id별로 처음 등장한 Document를 남긴 목록입니다.
            빈 목록을 받으면 빈 목록을 반환합니다.
    
    검색 점수를 다시 계산하거나 전체 관련성 순위로 정렬하지 않습니다.
    """
    by_id = {}
    for doc in documents:
        source_id = doc.metadata["source_id"]
        if source_id not in by_id:
            by_id[source_id] = doc
    return list(by_id.values())

# 본문과 조건 메타데이터를 함께 줘 연도·분류·쪽수도 답변에서 확인할 수 있게 합니다.
def format_context(documents):
    """검색 원문을 답변 프롬프트의 context에 넣을 문자열로 묶습니다.
    
    매개변수:
        documents (list[Document]): 검색으로 찾은 원문 목록.
            각 문서의 metadata에 source_id와 title이 있어야 합니다.
    
    반환값:
        str: 문서마다 [원문 ID], 제목, 메타데이터, 본문을 담고 빈 줄로 구분한 문자열.
            빈 목록을 받으면 빈 문자열을 반환합니다.
    
    답변 모델은 본문을 근거로 답하고 [원문 ID]를 인용합니다. 메타데이터도 포함하므로
    분류·출판 연도 같은 조건을 함께 읽을 수 있습니다. 이 함수는 모델을 호출하지 않습니다.
    """
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
    """다섯 질의 변환 방법에 필요한 프롬프트·체인·검색기 객체를 준비합니다.
    
    매개변수:
        llm: 질의 변환을 수행할 채팅 모델 객체.
        vector_store (Chroma): Self-Query에 연결할 원문 벡터 저장소.
        hybrid (EnsembleRetriever): Multi-Query에 연결할 하이브리드 검색기.
        k (int): Self-Query 검색 설정에 넣을 문서 수.
    
    반환값:
        dict: 방법 이름으로 해당 객체를 꺼낼 수 있는 딕셔너리입니다.
            self_query: 검색어와 메타데이터 필터를 추출하는 SelfQueryRetriever.
            hyde: 검색에 사용할 가상 소개문을 만드는 체인.
            multi_query: 같은 뜻의 검색 질문을 만드는 MultiQueryRetriever.
            step_back: 배경 원리를 묻는 질문을 만드는 체인.
            decomposition: 하위 질문 목록을 SubQuestions 객체로 받는 체인.
    
    이 함수는 실행에 필요한 객체를 구성합니다. 실제 질의 변환 요청과 검색은
    retrieve가 해당 객체의 체인이나 검색기를 호출할 때 수행합니다.
    """
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
    """원문을 임베딩해 적재하고 여러 질문에서 재사용할 검색 환경을 만듭니다.
    
    매개변수:
        records (list[dict]): make_documents에 전달할 원문 기록 목록.
        llm: 다섯 질의 변환 방법에서 사용할 채팅 모델 객체.
        embedding_model: 원문과 검색 입력의 벡터를 생성할 임베딩 모델 객체.
        k (int): 기본 검색 개수. 기본값은 3입니다.
        collection_name (str): Chroma 컬렉션 이름. 기본값은 day47_jev_router_books입니다.
    
    반환값:
        dict: retrieve의 retrieval 인자로 전달할 검색 환경입니다.
            vector_store: 원문과 벡터를 적재한 Chroma 저장소.
            bm25, dense: 단어 기반 검색기와 벡터 기반 검색기.
            hybrid: 두 결과를 가중치 0.5·0.5, RRF c=60으로 합치는 검색기.
            transforms: 다섯 질의 변환 객체를 담은 딕셔너리.
            k: 설정한 기본 검색 개수.
            document_count: 적재한 원문 수.
    
    같은 이름의 컬렉션을 초기화하고 입력 원문 전체의 임베딩을 생성해 적재합니다.
    여러 질문을 검색할 때는 이 함수를 한 번 호출하고 반환된 딕셔너리를 재사용합니다.
    이 단계에서 질의 변환이나 최종 답변 생성을 위한 LLM 호출은 수행하지 않습니다.
    """
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
    """선택한 질의 변환과 하이브리드 검색을 실행해 원문과 검색 입력 기록을 반환합니다.
    
    매개변수:
        question (str): 사용자가 처음 입력한 질문.
        method (str): self_query, hyde, multi_query, step_back, decomposition 중 하나.
            Jev의 선택과 confidence 기준을 적용한 뒤 전달합니다.
        retrieval (dict): prepare_retrieval이 반환한 검색 환경.
            저장소, 검색기, 질의 변환 체인, 기본 검색 개수 k를 재사용합니다.
    
    반환값:
        tuple[list[Document], dict]: found, trace 순서의 두 값을 반환합니다.
            found: 검색으로 찾은 원문 목록. 검색 조건에 맞는 원문이 없으면 빈 목록입니다.
                Self-Query·HyDE는 최종 상위 k개를 사용합니다. Multi-Query는 질문별
                검색 결과 전체를, Step-back·Decomposition은 질문별 상위 k개를 합쳐
                중복을 제거하므로 최종 원문 수가 k보다 많을 수 있습니다.
            trace: 검색에 실제로 사용한 입력을 확인하기 위해 이 함수가 만드는 dict입니다.
                self_query: queries에는 검색어 목록, filter에는 메타데이터 조건을 담습니다.
                    조건이 없으면 filter는 None입니다.
                hyde: bm25_query에는 원질문, hypothetical_text에는 Dense 검색에
                    사용한 가상 소개문을 담습니다.
                multi_query: queries에 원질문과 같은 뜻으로 변환한 질문들을 담습니다.
                step_back: queries에 원질문과 배경 원리를 묻는 질문을 담습니다.
                decomposition: queries에 원질문을 나눈 하위 질문들을 담습니다.
    
    사용 예:
        found, trace = retrieve(question, method, retrieval)
        # Self-Query의 trace 구조 예: {"queries": ["천체의 일생"], "filter": {"year": {"$lt": 2018}}}
        # HyDE의 trace 구조 예: {"bm25_query": "사용자의 원질문", "hypothetical_text": "생성한 소개문"}
    
    최종 답변에는 found의 원문을 사용합니다. trace는 변환된 질문과 검색 조건을
    확인하는 기록이며, Jev의 응답이나 최종 답변이 아닙니다. 이 함수는 질의 변환
    모델과 검색기를 호출하며 최종 답변 생성은 노트북의 answer_chain에서 수행합니다.
    
    예외:
        ValueError: 지원하지 않는 method가 전달된 경우. clarify는 검색을 보류하는
            상태이므로 이 함수를 호출하기 전에 run_rag에서 처리합니다.
    """
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
