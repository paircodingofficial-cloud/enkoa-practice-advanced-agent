"""기존 영화·의약품 패킷 읽기와 배포 벡터 대응 검사. 검색 로직은 교안에 있습니다."""
import json
import hashlib
from pathlib import Path

def load_graph(path):
    """배포 패킷에서 그래프·문서·청크를 읽습니다."""
    from langchain_core.documents import Document

    path = Path(path)
    raw = path.read_bytes()
    data = json.loads(raw)
    signature = hashlib.sha256(raw)
    data["fingerprint"] = signature.hexdigest()
    data["chunks"], data["source_links"], data["document_links"] = [], [], []
    for run in data["builder_runs"]:
        document = run["document"]
        for node in run["graph"]["nodes"]:
            if node["label"] == "Chunk":
                assert node["embedding_ref"]["index"] == len(data["chunks"]), "패킷의 벡터 행 순서를 확인하세요."
                data["chunks"].append(Document(
                    page_content=node["properties"]["text"],
                    metadata={"chunk_id": node["id"], "source_doc_id": document["doc_id"],
                              "title": document["title"], "url": document["url"]},
                ))
        for edge in run["graph"]["relationships"]:
            if edge["type"] == "FROM_CHUNK":
                data["source_links"].append({"standard_id": edge["start_node_id"],
                    "chunk_id": edge["end_node_id"], **edge["properties"]})
            elif edge["type"] == "ABOUT_MOVIE":
                data["document_links"].append({"doc_id": edge["start_node_id"],
                                               "standard_id": edge["end_node_id"]})
    return data

def read_vectors(path, chunks, embedding_model):
    """배포 벡터가 현재 원문·청크·임베딩 모델과 대응하는지 검사합니다."""
    import numpy as np

    # 파일은 강사가 한 번 생성합니다. 누락 시 학생에게 재임베딩을 시키지 않습니다.
    if not path.exists():
        raise FileNotFoundError(f"배포 임베딩 파일이 없습니다: {path}. data/embeddings 폴더를 확인하세요.")
    ids = [chunk.metadata["chunk_id"] for chunk in chunks]
    signature = hashlib.sha256()
    for chunk in chunks:
        signature.update(json.dumps([chunk.metadata, chunk.page_content], ensure_ascii=False, sort_keys=True).encode())
    fingerprint = signature.hexdigest()
    with np.load(path, allow_pickle=False) as saved:
        # 원문·순서·모델·차원이 다른 벡터를 잘못 적재하지 않도록 확인합니다.
        if saved["fingerprint"].item() != fingerprint or saved["chunk_ids"].tolist() != ids:
            raise ValueError("원문과 배포 임베딩이 다릅니다. 같은 버전의 data 폴더를 사용하세요.")
        if saved["model"].item() != embedding_model.model or int(saved["dimensions"].item()) != embedding_model.dimensions:
            raise ValueError("배포 파일과 질문 임베딩의 모델·차원이 다릅니다.")
        vectors = saved["vectors"]
        if vectors.shape != (len(chunks), embedding_model.dimensions) or not np.isfinite(vectors).all():
            raise ValueError("배포 임베딩의 개수·차원·수치를 확인하세요.")

    return ids, vectors
