# Graph·Vector 하이브리드 검색 심화

영화 자료로 벡터 검색·전문 검색·그래프 관계를 연결하고, 근거를 인용한 답변을 만듭니다.

## 학습 순서

| 자료 | 내용 |
|---|---|
| [교안 01](교안_01_벡터진입_관계확장.ipynb) | VectorCypherRetriever로 출연 관계 확장, Jev 언어 판단과 전문 검색 |
| [교안 02](교안_02_통합검색_멀티홉답변.ipynb) | GraphCypherQAChain, 가중 RRF, PageRank 재정렬, 멀티홉 근거 답변 |
| [과제 LV1](과제_LV1_기초.ipynb) | 교안 01의 검색·관계 확장 로직 직접 작성 |
| [과제 LV2](과제_LV2_응용.ipynb) | 교안 02의 통합 검색·재정렬·인용 답변 직접 작성 |

각 교안 마지막의 **핵심 코드 이어서 보기**는 본문에서 DB를 적재한 뒤 검색 흐름을 이어 실행합니다.
진행 순서는 [실습 가이드](실습_가이드.md)를 참고하세요.

## 환경 준비

1. 저장소 루트에서 `uv sync --frozen`을 실행합니다.
2. VS Code 커널로 저장소의 `.venv`를 선택합니다.
3. **Neo4j 2026.09 이상·Cypher 25**인 실습 DB에 해당 버전과 호환되는 **GDS·APOC**를 설치합니다.
4. 이 폴더의 `.env.example`을 `.env`로 복사하고 아래 연결 정보를 입력합니다.

| 환경변수 | 설정 |
|---|---|
| `OPENAI_API_KEY` | 질문 임베딩·검색어 변환·답변 생성에 사용할 키 |
| `TYPESAFE_API_KEY` | Jev 언어 판단에 사용할 키 |
| `TYPESAFE_MODEL` | `jev-1.13.0` |
| `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | 실습 DB의 Bolt 주소·계정 |
| `NEO4J_READONLY_USERNAME`, `NEO4J_READONLY_PASSWORD` | 교안 02의 관계 조회 계정 |

공유 DB는 실제 조회 전용 계정을 사용하세요. Community에서는 학습 데이터만 있는 별도 DB의 계정을 사용합니다. 변수명만으로 권한이 제한되지는 않습니다.

새 서버의 `neo4j.conf`에서 `db.query.default_language=CYPHER_25`를 설정합니다. 기존 DB는 관리 계정으로 system DB에서 다음을 실행합니다.

```cypher
// 사용할 실습 DB의 기본 쿼리 언어를 Cypher 25로 설정합니다.
ALTER DATABASE neo4j SET DEFAULT LANGUAGE CYPHER 25;
```

Neo4j 버전은 전문 검색의 `SEARCH ... FULLTEXT INDEX` 문법에 필요합니다. GDS·APOC는 Python 패키지와 별도로 Neo4j 서버에 설치합니다.
[SEARCH 공식 문법](https://neo4j.com/docs/cypher-manual/25/clauses/search/) · [GDS 설치](https://neo4j.com/docs/graph-data-science/current/installation/) · [APOC 설치](https://neo4j.com/docs/apoc/current/installation/)

노트북 파일이 있는 폴더에서 실행하세요. 교안 01의 적재를 먼저 완료한 뒤 교안 02·과제를 진행합니다.

## 데이터와 모델 호출

영화 38편·인물 133명·관계 253건, 원문 38편·청크 571개를 사용합니다.
문서 벡터는 함께 배포한 `text-embedding-3-large` 768차원 파일을 재사용합니다. [데이터 출처](data/README.md)

- 벡터 검색은 질문만 임베딩합니다.
- 전문 검색은 매번 Jev를 호출하고, 한글일 때만 영어 검색어 변환 모델을 호출합니다.
- 교안 02는 관계 Cypher와 최종 답변 생성에도 모델을 호출합니다.
- 이미 받은 검색 결과와 질문 벡터는 비교 실습에서 재사용합니다.
