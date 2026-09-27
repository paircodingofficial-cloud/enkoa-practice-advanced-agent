# 재사용한 영화 데이터

이 폴더는 `실습자료/day42_도메인_GraphRAG/data/`의 배포 데이터를 복사한 것입니다.
새로운 개체·관계·줄거리·청크·임베딩을 생성하지 않았습니다.

| 파일 | 내용 |
|---|---|
| `movies_extraction_packet.json` | 개체 171개·관계 253건, 원문 38편, 기존 builder_runs 청크 571개와 출처 연결 |
| `movies_sample_full.json` | Neo4j Movies 원본 샘플 전체 |
| `movies_wikipedia_texts.json` | 도입부와 전체 줄거리, 원문 revision ID와 URL |
| `movies_schema.json` | 기존 그래프의 노드·관계 정의 |
| `movies_questions.json` | 기존 자료의 질문과 관계 근거 ID 참고용 |
| `embeddings/movies_complete.npz` | 571개 청크에 대응하는 768차원 OpenAI 배포 벡터 |
| `embeddings/manifest.json` | 기존 배포 파일의 모델·차원·fingerprint·sha256 기록 |
| `sources.json` | 기존 출처 기록의 movies 항목 |

## 출처와 재사용 조건

- 관계·영화 속성: [Neo4j Movies 샘플](https://github.com/neo4j-graph-examples/movies). 이전 교안에서 고정한 샘플의 값과 관계 속성을 유지합니다.
- 줄거리: [Wikipedia](https://en.wikipedia.org/). 각 문서의 `url`은 이전 자료에서 사용한 고정 revision 주소입니다. 텍스트의 재사용 조건은 **CC BY-SA 4.0**입니다. 문서별 URL과 revision ID는 `movies_wikipedia_texts.json`에 있습니다.
- 원문은 영어입니다. 학습자는 한글 질문을 입력하며, 전문 검색 함수는 Jev로 언어를 판단해 한글은 영어 핵심어 목록으로 변환하고 영어는 그대로 조회합니다.

관계 정보와 줄거리 정보는 서로 다른 자료에서 왔습니다. 출연 관계를 Wikipedia 청크에서 추출한 결과라고 표시하지 않습니다.
기존 샘플은 전체 영화계 데이터가 아니며, 샘플에 없는 출연 관계를 없다고 일반화하지 않습니다.

## 노트북에서 저장하는 구조

```text
Chunk -[:FROM_DOCUMENT]-> Document -[:ABOUT_MOVIE]-> Movie
Person -[:ACTED_IN]-> Movie
```

원래 standard_id·문서 ID·청크 ID·claim_id를 그대로 사용합니다. 영화·인물에는 공통 ID 조회와 고유 제약을 위한 `RAGEntity` 레이블을 함께 붙입니다.
다른 종류의 기존 관계도 적재하지만, 이번 확장과 중심성 계산은 `ACTED_IN`만 사용합니다.


# 과제에서 재사용하는 의약품 데이터

단위프로젝트2_개편/version_c_drugs의 e약은요 원문 519건 중 day42에서 선정·배포한 14건을 그대로 재사용합니다. 14개 문서는 두통·감기약 5, 멀미약 3, 제산제 2, 변비약 3, 지사제 1로 구성됩니다. 전체 519건을 적재하는 과제가 아닙니다.

| 파일 | 내용 |
|---|---|
| drugs_extraction_packet.json | 제품 원문 14개·청크 43개·개체 270개·도메인 관계 459개 |
| drugs_sources.json | 원본 corpus/triples 해시, 추출·선정 이력, 표기 수정과 출처 |
| drugs_schema.json | 의약품 그래프의 노드·관계 정의 |
| embeddings/drugs.npz | 기존 text-embedding-3-large 768차원 벡터 43개 |
| embeddings/drugs_manifest.json | 배포 모델·차원·fingerprint·파일 SHA-256 |

출처는 식품의약품안전처 의약품개요정보(e약은요)입니다. 원문 URL과 관계별 evidence·source_doc_id·claim_id를 함께 보존합니다. 원본 문서에 기존 배포본의 사용법·제조사 줄이 포함됩니다. 관계는 프로젝트의 추출 결과이며, 문서에서 언급하지 않은 관계까지 완전하게 담았다는 뜻은 아닙니다.

```text
DrugChunk -[:FROM_DOCUMENT]-> DrugDocument -[:ABOUT_DRUG]-> Drug
Drug -[:TREATS]-> Symptom
Drug -[:HAS_SIDE_EFFECT]-> Symptom
Drug -[:CAUTION_FOR]-> RiskGroup
Drug -[:CONTAINS]-> Ingredient
Drug -[:INTERACTS_WITH]-> Drug 또는 Ingredient
Drug -[:MADE_BY]-> Manufacturer
```

원래 개체 ID 앞에 day49:를 붙여 저장하고 문서·청크 ID·claim_id는 유지합니다. 개체에는 DrugEntity, Drug·Symptom에는 GDS 범위를 한정하는 DrugRankNode도 붙입니다. 문서·청크·연결을 포함하면 327노드·516관계입니다. Drug 45개 중 문서가 있는 제품은 14개이며, 나머지는 상호작용 대상 이름입니다. 영화용 Chunk·Document 레이블은 붙이지 않습니다.

과제의 전문 검색은 한국어 원문에 맞춘 standard-no-stop-words 분석기를 사용합니다. Jev 결과 ko는 그대로, en은 한국어 핵심어로 변환하여 조회합니다. 문서 벡터는 다시 생성하지 않습니다.

`build/prepare_medical_data.py --check`로 원본 프로젝트 해시와 day42 배포 파일의 동일성을 확인합니다. `--copy`는 검증한 파일을 다시 복사합니다.
