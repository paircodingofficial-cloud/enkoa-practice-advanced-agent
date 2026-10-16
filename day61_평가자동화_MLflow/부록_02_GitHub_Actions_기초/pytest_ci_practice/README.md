# pytest_ci_practice

day61 부록 02(GitHub Actions 기초)의 연습 프로젝트입니다. 이 폴더를 그대로 GitHub 저장소로 올립니다.

| 파일 | 내용 |
|---|---|
| `citation_check.py` | 교안 01의 `normalize`, `check_citation` |
| `gate_rules.py` | 교안 02 회귀 게이트 규칙을 함수로 옮긴 것 |
| `tests/` | 단위 테스트(`test_normalize.py`, `test_check_citation.py`)와 게이트 규칙 테스트(`test_gate_rules.py`) |
| `.github/workflows/tests.yml` | 처음 만드는 GitHub Actions 워크플로 |
| `design/ci.yml` | 부록 02 7절 요구사항을 반영하고 Ruff 검사와 AI 리뷰까지 넣은 완성 워크플로 |
| `tools/ai_reviewer.py` | (부록 02 9절에서 추가) 바뀐 코드를 LLM이 리뷰해 `review.md`로 저장하는 스크립트 |

```bash
uv sync
uv run pytest -v tests
```

부록 02 8절에서 추가한 Ruff 명령입니다.

```bash
uv run ruff check .            # 문법·스타일 규칙과 import 순서 검사
uv run ruff format --check .   # 포맷이 맞는지만 검사(파일은 바꾸지 않음)
uv run ruff format .           # 포맷을 실제로 고침
```

부록 02 9절에서 추가한 AI 리뷰 명령입니다. `OPENAI_API_KEY` 환경변수가 필요합니다.

```bash
git fetch origin main                                  # 비교할 main 브랜치를 최신으로 받음
uv run --group review python tools/ai_reviewer.py      # main 과 비교해 바뀐 코드를 리뷰하고 review.md 로 저장
```
