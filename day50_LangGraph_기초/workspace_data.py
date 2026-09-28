"""공유 작업실 과제의 배포 문서 벡터를 읽고 원문 대응을 확인합니다."""
import hashlib
import json
from pathlib import Path
import numpy as np


def read_workspace_vectors(path, documents, embedding_model):
    """문서 ID·본문·순서·모델·차원을 확인한 뒤 저장 벡터를 반환합니다."""
    path = Path(path)
    doc_ids = [doc.metadata['source_id'] for doc in documents]
    signature = hashlib.sha256(json.dumps(
        [[doc.metadata, doc.page_content] for doc in documents],
        ensure_ascii=False, sort_keys=True,
    ).encode()).hexdigest()
    with np.load(path, allow_pickle=False) as saved:
        if saved['fingerprint'].item() != signature or saved['doc_ids'].tolist() != doc_ids:
            raise ValueError('작업실 원문과 배포 벡터가 다릅니다. 같은 버전의 data 폴더를 사용하세요.')
        if saved['model'].item() != embedding_model.model or int(saved['dimensions'].item()) != embedding_model.dimensions:
            raise ValueError('질문 임베딩의 모델과 차원을 배포 벡터에 맞추세요.')
        vectors = saved['vectors']
        if vectors.shape != (len(documents), embedding_model.dimensions) or not np.isfinite(vectors).all():
            raise ValueError('배포 벡터의 개수·차원·수치를 확인하세요.')
    return doc_ids, vectors
