# 도서관 안내 RAG 회귀 게이트

도서관 안내 RAG 앱을 변경 요청마다 골든셋으로 평가하고, 기준선보다 품질이 떨어지면 GitHub Actions 검사를 실패시켜 병합을 막는 프로젝트입니다. 이 폴더를 그대로 저장소 하나로 올려 씁니다.

## 구조

```text
rag_eval_ci/
├── app.py                          RAG 앱(TOP_K, 프롬프트). 변경 요청은 보통 이 파일을 고칩니다
├── run_eval.py                     골든셋으로 app.py 를 평가해 reports/ 에 결과를 남깁니다
├── data/                           문서(docs.jsonl), 골든셋(golden.jsonl), 문서 벡터(chroma/)
├── baselines/baseline.json         사람이 승인한 기준선
├── tests/test_rag_regression.py    결과를 기준선과 비교해 통과·실패를 판정합니다
├── .github/workflows/rag-eval.yml  변경 요청마다 평가와 테스트를 돌리는 워크플로
└── pyproject.toml, uv.lock         고정한 라이브러리 버전
```

`reports/`(평가 결과)는 실행할 때 생기며 저장소에 올리지 않습니다.

## 흐름

1. `run_eval.py`가 평가만 하고 결과를 `reports/results.json`에 씁니다.
2. pytest가 이 파일과 `baselines/baseline.json`을 읽어 판정합니다. 실패하면 종료 코드가 0이 아니라 CI 검사가 실패합니다.
3. 변경 요청은 대표 6건(`smoke`), 매일 예약 실행과 직접 실행은 전체 16건(`full`)을 평가합니다.

## 실행

```bash
uv sync
uv run python run_eval.py --split smoke
uv run pytest -q tests
```

API 키는 로컬에서는 `.env`의 `OPENAI_API_KEY`로, GitHub에서는 Settings > Secrets and variables > Actions에 같은 이름으로 등록합니다.
