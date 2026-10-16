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
| **day53** | CRAG·Self-RAG 응용 | 근거 평가·재검색·웹 보완, 답변 검토·수정과 종료 조건. 팝업·전시 플래너와 게임 소개 대본 검수 과제 |
| **day55** | 멀티에이전트 협업 | 슈퍼바이저가 `Command(goto, update)`로 워커에게 일을 나누고, 계획에 따라 `Send`로 병렬 실행한 결과를 리듀서로 합칩니다. `Command.PARENT` 핸드오프와 검수 루프, 라운드 상한을 익히고, MCP 도구를 쓰는 콘텐츠 분석 팀과 콘텐츠 생성 팀을 `.py` 종합실습으로 완성합니다 |
| **day56** | 멀티에이전트 관측·실패 처리 | **Langfuse**로 멀티에이전트 실행을 trace 로 남겨 궤적에서 원인을 찾고, 핑퐁 반복·재시도(`RetryPolicy`)·노드 타임아웃을 막습니다. 병렬 작업의 부분 실패와 폴백, 체크포인트에서 이어 하기와 분기 실행(fork)을 다루고, 병원 예약 상담 팀 관측과 택배 지연 대응 팀 실패 처리 과제로 적용합니다 |
| **day57** | GraphRAG 변형 비교 | **Microsoft GraphRAG**(`graphrag` 3.1.0)로 관광지 안내문을 색인해 개체·관계·계층 커뮤니티·커뮤니티 보고서를 만들고 **Basic·Local·Global·DRIFT** 네 검색이 답변 모델에 넘긴 근거를 비교합니다. 이어서 **LightRAG**(`lightrag-hku` 1.5.7)로 구체·주제 키워드 검색과 문서 추가·삭제를 다루고, 부록에서 LazyGraphRAG·HippoRAG 2 와 네 방식의 비용·근거를 질문 유형(단일 사실·멀티홉·전역)별로 비교합니다. 과제는 의약품 안내문에 두 방식을 적용합니다 |
| **day58** | RAG 아키텍처 설계 | 임베딩 모델·검색 전략·벡터 저장소를 리더보드 순위나 기본값이 아니라 같은 평가셋으로 고릅니다. 교안 01은 MTEB(kor) 후보와 BM25를 **Recall@5·MRR·걸린 시간·비용·잘림 비율**로 비교하고 차원과 정밀도를 낮춰 저장 공간을 줄입니다. 교안 02는 질문 유형(묘사·이름·조건·관계·집계)마다 검색 전략을 측정하고, 그 전략에 필요한 질의로 벡터 저장소(**pgvector**)를 고른 뒤 정확도·지연·비용·저장 공간 네 축을 **제약·지배 제거·가중 점수·민감도** 순서로 종합해 결정을 **ADR**로 남깁니다. 과제는 의약품 안내문에 같은 절차를 적용합니다 |
| **day59** | LLM 평가·RAGAS | RAG 답변과 검색 결과를 **RAGAS**(`ragas` 0.4.3) 지표 6종으로 평가합니다. 교안 01은 결함을 일부러 넣은 답변으로 **Faithfulness·Answer Relevancy·Answer Correctness**가 결함마다 어떻게 떨어지는지 보고, 두 지표를 함께 읽어 결함 종류와 고칠 곳을 가립니다. 교안 02는 **Context Precision·Context Recall·Context Relevancy**를 더해 지표 6개의 합격선 판정과 기준선 비교로 RAG의 고장 위치(검색·생성)를 진단합니다. 과제는 의약품 상담 도우미에 같은 절차를 적용합니다 |
| **day60** | LLM-as-Judge·DeepEval | 판사 모델의 점수화·쌍대 비교와 위치·장황함 편향을 살펴보고, **DeepEval**(`deepeval` 4.2.9)의 G-Eval·ArenaGEval·Hallucination·Toxicity·Bias 지표로 답변을 평가합니다. 사람 라벨과 비교해 판정 기준과 테스트 케이스를 점검합니다. 부록은 골든셋과 Jev 판사로 챗봇 프롬프트를 자동으로 고칩니다(`PromptOptimizer`) |
| **day61** | 평가 자동화·MLflow | 골든셋 평가를 **MLflow**(`mlflow` 3.14.0)에 기록하고, DeepEval 판사(정답 판정·검색 근거 판정)와 코드 채점(인용 검증)을 채점 함수(`@scorer`)로 붙여 실행 기록(trace)과 함께 비교합니다. 교안 02는 같은 설정을 반복 평가해 판정 흔들림을 확인하고, 기준선·**pytest** 회귀 테스트·**GitHub Actions**/GitLab CI 회귀 게이트를 만듭니다. 부록은 MLflow GenAI 화면, pytest 기초, GitHub Actions 기초, GitHub Actions 심화(Ruff 코드 검사와 AI 코드 리뷰) |

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

day52는 Mem0·Qdrant·SQLite를 사용합니다.

day53은 단원 폴더의 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`와 `TAVILY_API_KEY`를 설정합니다. Tavily 키는 [대시보드](https://app.tavily.com/)에서 발급받습니다. 과제02는 웹 검색을 사용하지 않습니다.

day55 교안·과제는 단원 폴더의 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`를 넣습니다. 종합실습01·02는 MCP 서버를 `npx`로 띄우므로 **Node.js 22 이상**이 필요하고, 프로젝트 폴더마다 있는 `.env.example`을 따로 `.env`로 복사해 키를 채웁니다. 설치와 실행 방법은 [종합실습01 README](day55_멀티에이전트_협업/종합실습01/starter/README.md)에 있습니다.

day56은 단원 폴더의 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`와 Langfuse 키(`LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`)를 넣습니다. Langfuse 키는 [cloud.langfuse.com](https://cloud.langfuse.com)에서 프로젝트를 만든 뒤 Settings > API Keys 에서 발급합니다. 화면 사용법은 `부록_Langfuse_화면_안내.ipynb`에 있습니다.

day57은 단원 폴더의 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`와 `TYPESAFE_API_KEY`를 넣습니다. 색인이 오래 걸리면 교안의 색인 셀 대신 미리 만든 색인을 복사하는 셀을 실행합니다(`data/*/prebuilt/`). `output/`에는 강사가 실행해 둔 교안 01·02 본실습 색인이 들어 있습니다. 교안 02 함께 따라하기는 day48과 같은 Qwen3-Reranker-0.6B를 씁니다.

day58은 단원 폴더의 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`(교안 01 임베딩, 약 7센트)와 `SUPABASE_DB_URL`(교안 02)을 넣습니다. Supabase 주소 만드는 법은 [Supabase_접속_주소_만들기.md](day58_RAG_아키텍처_설계/Supabase_접속_주소_만들기.md)에 있습니다. 과제 02는 내 PC의 Neo4j(2026.06 이상) 접속 정보(`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`)도 넣습니다. 교안 01은 로컬 임베딩 모델 `intfloat/multilingual-e5-small`(약 0.5GB)과 `nlpai-lab/KURE-v1`(약 2.3GB)을 내려받으므로 수업 전에 첫 코드 셀만 먼저 실행해 두세요.

day59는 단원 폴더의 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`를 넣습니다. 평가용 LLM은 코드 기본값 `gpt-6-luna`를 쓰므로 따로 적지 않아도 됩니다(ragas 0.4.3은 `gpt-5.6-luna`처럼 버전에 소수점이 든 이름에서 요청 오류가 납니다). 교안 02·과제 02는 미리 만든 Chroma DB(`data/*/chroma/`)를 그대로 여니 폴더를 통째로 둡니다. 평가 셀은 평가용 LLM을 동시에 호출하며 상한은 `MAX_CONCURRENCY = 32`입니다. 429 오류가 나면 이 값을 줄입니다.

day60은 단원 폴더의 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`를 넣습니다. DeepEval은 `uv sync`에 포함된 4.2.9를 사용합니다. G-Eval의 logprobs 지원 때문에 판사 모델을 바꿀 때는 해당 모델이 logprobs를 지원하는지 확인하세요. 부록의 Jev 판사는 `TYPESAFE_API_KEY`가 필요합니다.

day61은 단원 폴더의 `.env.example`을 `.env`로 복사하고 `OPENAI_API_KEY`를 넣습니다(교안 01의 Jev 소절은 선택이며 `TYPESAFE_API_KEY`가 필요합니다). MLflow 화면은 단원 폴더에서 `uv run mlflow server --backend-store-uri sqlite:///mlflow.db --port 5050`으로 켭니다. 교안 02의 `rag_eval_ci/`와 부록 02의 `pytest_ci_practice/`는 자기 `pyproject.toml`이 있는 별도 프로젝트라, 그 폴더를 GitHub 저장소로 올려 씁니다.

## 폴더 구성

| 경로 | 내용 |
|---|---|
| `dayNN_*/교안_*.ipynb` | 수업에서 함께 실행하는 교안. 「함께 따라하기」 칸은 직접 작성합니다 |
| `dayNN_*/과제_*.ipynb` | 단원별 실습 과제. 제공 코드·작성 칸·확인 기준에 따라 진행합니다 |
| `dayNN_*/data`, `images` | 실습 입력 원문과 교안 그림 |
| `day55_*/종합실습NN/starter` | `.py` 종합실습 프로젝트. README 의 TODO 정리 순서대로 코드를 채웁니다 |
| `내작업/` | 여러분의 실습 공간. 깃이 추적하지 않습니다 |
