# 고급 RAG·에이전트 실습자료

엔코아 AI캠퍼스 「데이터 분석 & AI 머신러닝 캠프」 **GraphRAG 시스템 및 고도화** 과목의 앞부분(고급 RAG·에이전트·평가) 실습용 주피터 노트북입니다. 수업 진도에 맞춰 자료가 추가됩니다.

### 수록 자료

| 일차 | 주제 | 배우는 것 |
|---|---|---|
| **day46** | 청킹 전략·RAPTOR | 기본 RAG가 근거를 놓치는 두 자리를 확인하고, **Fixed·Semantic·Parent-Child·Sentence Window·Auto-merging** 다섯 전략으로 무엇으로 찾고 무엇을 돌려줄지 나눕니다. 같은 질문·근거·K로 **근거 구간 Recall과 반환 글자 수**를 함께 비교하고, 이어서 **RAPTOR**로 문장을 군집화해 GPT 요약 계층(L0 → L1 → L2)을 쌓은 뒤 모든 계층을 한 인덱스에서 검색하고 출처 문장으로 되돌아옵니다 |
| **day47** | 하이브리드 검색·질의 변환 | **BM25**(Kiwi 형태소)와 **Dense** 검색 순위를 **가중 RRF**·`EnsembleRetriever`로 합치고 Recall을 비교합니다. 이어서 **Self-Query·HyDE·Multi-Query·Step-back·Decomposition** 다섯 질의 변환으로 검색 입력을 바꿔 원문 근거로 답하고, 교안 03에서는 **Jev**(Noul·Choice·Score)가 질문마다 어떤 질의 변환을 쓸지 골라 실제 하이브리드 RAG로 이어 갑니다 |
| **day48** | 리랭킹·컨텍스트 압축 | 검색 후보를 **Cross-Encoder**(Qwen3-Reranker-0.6B)로 다시 점수 매겨 순서를 고치고, 같은 후보를 **ColBERT**(BGE-M3) 토큰 매칭으로도 재정렬해 비교한 뒤 `CrossEncoderReranker` 로 검색기와 리랭커를 연결합니다. 교안 02에서는 질문에 필요한 구간만 GPT로 **추출**해 답하고, 원문 답변과 추출 답변의 내용·**토큰 사용량**을 대조한 다음 검색 → 리랭킹 → 추출을 하나의 파이프라인으로 잇습니다 |
| **day49** | Graph·Vector 하이브리드 검색 | VectorCypherRetriever의 출연 관계 확장, Jev 언어 판단과 Neo4j 전문 검색, GraphCypherQAChain·가중 RRF·PageRank·멀티홉 근거 답변 |
| **day50** | LangGraph 기초 | State·노드·고정/조건부 엣지·메시지 리듀서, Jev와 하이브리드 RAG, 질문별 검색 도구 라우팅 |
| **day51** | LangGraph 사이클·HITL | 반복과 종료 조건, 체크포인터, 사람의 검토와 실행 재개 |
| **day52** | 메모리·컨텍스트 | Store·Mem0 기억 관리, 토큰 기반 요약과 입력 조절, 기억 갱신을 연결한 실습 |
| **day53** | CRAG·Self-RAG 스타일 | 검색 근거 평가·재검색, 답변 검토·수정, 부분 답변과 검색 실패 안내 |

---

## ⚠️ 딱 하나만 기억하세요

> ### 배포된 자료는 **읽기 전용**입니다.
> ### 실습은 **`내작업/` 폴더에 복사해서** 하세요.

셀을 실행만 해도 파일이 바뀔 수 있으니 원본은 건드리지 마세요. `내작업/` 안에서 만든 파일은 깃이 무시하므로 마음껏 고쳐도 됩니다.

```bash
mkdir -p 내작업
cp -r day46_청킹전략_RAPTOR 내작업/
```

자료가 업데이트되면 `git pull` 로 받습니다. 원본을 고쳐 두면 `pull` 이 충돌로 막힙니다. 그때는 아래를 실행하세요(바뀐 내용은 `.백업/` 에 보관됩니다).

```bash
uv run 업데이트.py
```

---

## 환경 준비

```bash
uv sync                      # pyproject.toml·uv.lock 그대로 설치
```

VS Code에서 노트북을 열고 커널로 **Python 3 (ipykernel)** 즉 위에서 만든 `.venv` 를 선택하세요.

OpenAI API를 쓰는 일차는 폴더의 `.env.example` 을 `.env` 로 복사하고 `OPENAI_API_KEY` 를 넣습니다. day47 교안 03과 day49는 `TYPESAFE_API_KEY`도 넣습니다. 키는 노트북에 붙여넣지 않습니다.

day48은 Hugging Face 리랭커 모델을 내려받아 CPU에서 실행합니다. 교안 01 첫 셀이 Qwen3-Reranker-0.6B(약 1.19GB)와 BGE-M3(약 2.3GB)를 한 번 받아 두면 이후 교안·과제는 캐시를 재사용합니다. 디스크 여유 공간 5GB 이상을 확보하고 수업 전에 미리 받아 두세요.

day49는 **Neo4j 2026.09 이상·Cypher 25·GDS·APOC**가 필요합니다. Python 패키지는 `uv sync --frozen`으로 설치하고, DB 연결은 [day49 환경 안내](day49_Graph_Vector_하이브리드/README.md)에 따라 설정하세요.

day50은 `langgraph`로 노드를 연결합니다. 교안 03은 Neo4j·APOC를 사용하며, 설정과 실행 순서는 [day50 README](day50_LangGraph_기초/README.md)를 따릅니다.

day52는 Mem0·Qdrant·SQLite를 사용합니다. day53은 공개 영화 검색 보완에 `TAVILY_API_KEY`를 사용하며, 자세한 설정은 [day53 README](day53_CRAG_SelfRAG/README.md)를 참고하세요.

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `dayNN_*/교안_*.ipynb` | 수업에서 함께 실행하는 교안. 「함께 따라하기」 칸은 직접 작성합니다 |
| `dayNN_*/과제_*.ipynb` | 단원별 실습 과제. 제공 코드·작성 칸·확인 기준에 따라 진행합니다 |
| `dayNN_*/data`, `images` | 실습 입력 원문과 교안 그림 |
| `내작업/` | 여러분의 실습 공간. 깃이 추적하지 않습니다 |
