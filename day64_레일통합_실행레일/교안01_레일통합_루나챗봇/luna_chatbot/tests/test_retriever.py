"""도구 층: 검색 저장소는 만들기(--build)와 열기를 나누고, 비어 있는 저장소는 열 때 바로 알린다."""
import pytest

from app.tools import retriever


def test_sections_have_ids():
    # 검색 단위는 절이고, 절마다 평가의 정답 문서 id 와 같은 source_id 가 있다
    sections = retriever.load_knowledge_documents()
    assert len(sections) > 0
    for doc in sections:
        assert doc.metadata["source_id"] != ""


def test_empty_store_fails_with_build_hint(monkeypatch, tmp_path):
    # 빈 폴더를 저장소로 열면 임베딩하지 않고 --build 안내와 함께 오류를 낸다(API 를 부르지 않는다)
    monkeypatch.setattr(retriever, "CHROMA_DIR", tmp_path / "chroma")
    with pytest.raises(RuntimeError, match="--build"):
        retriever.get_vector_store()
