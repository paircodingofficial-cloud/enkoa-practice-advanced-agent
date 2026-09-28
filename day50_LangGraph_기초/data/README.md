# 실습 데이터

## 영화 그래프와 원문

- `movies_extraction_packet.json`: day49에서 사용한 영화·인물·관계, 영어 원문 38편과 571개 청크를 보관합니다.
- `movies_wikipedia_texts.json`: 같은 원문의 제목·본문·revision ID·출처 URL입니다.
- `embeddings/movies_complete.npz`: 청크 순서에 대응하는 `text-embedding-3-large` 768차원 배포 벡터입니다.

관계·영화 속성은 [Neo4j Movies 예제](https://github.com/neo4j-graph-examples/movies), 줄거리는 각 문서에 기록된 [Wikipedia](https://en.wikipedia.org/) 고정 revision 페이지에서 가져왔습니다. Wikipedia 원문의 재사용 조건은 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)입니다. 원문의 제목·본문·출처를 유지했습니다.

교안 02는 청크를 BM25·메모리 Chroma로 검색합니다. 교안 03은 그래프와 원문을 Neo4j에 적재하고 영화 전용 `Day49MovieChunk` 레이블의 전문·벡터 인덱스를 사용합니다. `graph_data.py`가 청크·원문·벡터 대응을 확인합니다. 실습에서는 질문만 임베딩합니다.

## 공유 작업실 안내문

- `workspace_faq.json`: 카메라 대여·장비 교육·예약 취소·보관·운영 시간 등을 설명하는 학습용 가상 안내문 8개입니다. 실제 시설 정책이 아닙니다.
- `embeddings/workspace_faq.npz`: 같은 문서의 768차원 배포 벡터입니다.
- `embeddings/workspace_faq.meta.json`: 벡터 생성 모델·차원 등 배포 정보입니다.

각 안내문은 `doc_id`, `title`, `text`, `source`로 구성됩니다. `workspace_data.py`가 문서 ID·순서·본문·벡터 대응을 확인합니다. 문서와 벡터는 같은 버전의 파일을 함께 사용하세요.

## 노트북 안의 업무 자료

교안 01의 고객지원 정책·문의·회의 메모와 과제 LV1의 장애 보고서·대응 절차는 학습용 가상 자료입니다. 실제 업체 정책이나 사고 기록이 아닙니다.
