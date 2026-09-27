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
