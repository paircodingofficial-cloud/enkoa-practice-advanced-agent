"""도구 층: 검색 문서(knowledge/*.md)를 절 단위로 나눠 Chroma 에 담고, 질문과 가까운 절을 찾는다.

검색 단위는 '## [절 id] 제목' 으로 시작하는 절 하나다. 절 id 는 메타데이터 source_id 에 둔다(평가의 정답 문서 id 와 같다).
저장소 만들기(build_vector_store)와 열기(get_vector_store)를 나눈다. 만들기는 준비 단계에서 한 번 실행한다.
  uv run -m app.tools.retriever --build   (임베딩 API 를 부른다. knowledge/*.md 를 고쳤을 때도 다시 실행한다)
"""
import re
import sys

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    DOCUMENT_SEPARATOR,
    KNOWLEDGE_DIR,
    embedding_model,
)

# 절 머리 줄: "## [tkt-01] 「Lumi Night」 서울 팬미팅 공지" 에서 절 id 와 제목을 꺼낸다
SECTION_PATTERN = re.compile(r"^## \[([^\]]+)\] (.+)$")


# [보조 함수] 절 본문 만들기
def join_body(lines: list) -> str:
    """절 본문 줄 목록을 빈 줄 없이 이은 문자열로 돌려준다."""
    # 절 안의 빈 줄을 지운다. 빈 줄이 남으면 DOCUMENT_SEPARATOR 로 나눌 때 절 하나가 여러 조각으로 쪼개진다
    kept = []
    for line in lines:
        # 공백뿐인 줄은 버리고 글자가 있는 줄만 남긴다
        if line.strip():
            kept.append(line)
    return "\n".join(kept)


# [보조 함수] 마크다운 한 파일을 절로 나누기
def read_sections(path) -> list:
    """마크다운 파일 하나를 절 단위 Document(본문, 메타데이터 source_id, title, file) 목록으로 돌려준다."""
    # 지금 읽는 절의 id, 제목, 본문 줄. 절 머리를 만나기 전에는 id 가 None 이다
    documents = []
    section_id = None
    title = ""
    body_lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SECTION_PATTERN.match(line)

        # 새 절 머리를 만나면 앞 절을 Document 로 저장하고 새 절을 시작한다
        if match:
            # 앞 절이 있었으면(첫 절이 아니면) 저장한다
            if section_id is not None:
                documents.append(Document(
                    page_content=join_body(body_lines),
                    metadata={"source_id": section_id, "title": title, "file": path.stem},
                ))
            section_id = match.group(1)
            title = match.group(2)
            body_lines = []

        # 첫 절 앞의 문서 제목 줄("# 공연 티켓 안내")은 건너뛴다
        elif section_id is not None:
            body_lines.append(line)

    # 마지막 절은 다음 머리가 없으므로 반복이 끝난 뒤 저장한다
    if section_id is not None:
        documents.append(Document(
            page_content=join_body(body_lines),
            metadata={"source_id": section_id, "title": title, "file": path.stem},
        ))
    return documents


# [도구 함수] 검색 문서 전체 읽기
def load_knowledge_documents() -> list:
    """knowledge 폴더의 모든 마크다운 파일을 절 단위 Document 목록으로 돌려준다."""
    documents = []
    # 파일 이름 순서로 읽어 실행할 때마다 같은 순서가 나오게 한다
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        documents.extend(read_sections(path))
    return documents


# [보조 함수] Chroma 컬렉션 연결
def open_chroma() -> Chroma:
    """output/chroma 의 검색 문서 컬렉션에 연결한 Chroma 객체를 돌려준다(임베딩 API 를 부르지 않는다)."""
    return Chroma(
        collection_name=CHROMA_COLLECTION,
        embedding_function=embedding_model,
        persist_directory=str(CHROMA_DIR),
    )


# [도구 함수] 벡터 저장소 만들기
def build_vector_store() -> Chroma:
    """컬렉션을 비우고 knowledge 폴더의 절 전체를 임베딩해 넣은 저장소를 돌려준다(임베딩 API 를 부른다)."""
    vector_store = open_chroma()

    # 문서를 고친 뒤 다시 만들 때 옛 절이 남지 않게 컬렉션을 비운다
    vector_store.reset_collection()

    # ids 에 절 id 를 주면 절 id 로 다시 꺼낼 수 있다(get_by_ids)
    documents = load_knowledge_documents()
    ids = []
    for doc in documents:
        ids.append(doc.metadata["source_id"])
    vector_store.add_documents(documents, ids=ids)
    return vector_store


# [도구 함수] 벡터 저장소 열기
def get_vector_store() -> Chroma:
    """만들어 둔 검색 문서 벡터 저장소를 돌려준다. 비어 있으면 오류를 낸다(임베딩 API 를 부르지 않는다)."""
    vector_store = open_chroma()

    # 빈 저장소로 검색하면 오류 없이 문서 0개가 나와 답이 조용히 틀어지므로 바로 알린다
    if len(vector_store.get()["ids"]) == 0:
        raise RuntimeError("검색 문서 저장소가 비어 있습니다. 프로젝트 폴더에서 uv run -m app.tools.retriever --build 를 먼저 실행하세요")
    return vector_store


# [보조 함수] 검색 문서를 프롬프트용 문자열로
def format_documents(docs: list) -> str:
    """검색 문서를 "[절 id] 제목" 줄과 본문으로 묶어 하나의 문자열로 돌려준다."""
    # 절마다 머리 줄을 붙여, 모델과 사실 대조 레일이 어느 절의 내용인지 구분하게 한다
    blocks = []
    for doc in docs:
        blocks.append(f"[{doc.metadata['source_id']}] {doc.metadata['title']}\n{doc.page_content}")
    return DOCUMENT_SEPARATOR.join(blocks)


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.tools.retriever
    # --build 를 붙이면 저장소를 새로 만든다(절 수만큼 임베딩 API 를 부른다). 붙이지 않으면 절 나누기만 확인한다
    sections = load_knowledge_documents()
    print("절 수:", len(sections))
    if "--build" in sys.argv:
        store = build_vector_store()
        print("저장소를 만들었습니다:", CHROMA_DIR, "/ 넣은 절 수:", len(store.get()["ids"]))
    else:
        for doc in sections[:3]:
            print("-", doc.metadata["source_id"], doc.metadata["title"], "/ 글자 수:", len(doc.page_content))
        print("저장소 폴더 있음:", CHROMA_DIR.exists())
        print(format_documents(sections[:1]))
