# pytest_ci_practice

day61 부록 02(GitHub Actions 기초)의 연습 프로젝트입니다. 이 폴더를 그대로 GitHub 저장소로 올립니다.

| 파일 | 내용 |
|---|---|
| `citation_check.py` | 교안 01의 `normalize`, `check_citation` |
| `gate_rules.py` | 교안 02 회귀 게이트 규칙을 함수로 옮긴 것 |
| `tests/` | 단위 테스트(`test_normalize.py`, `test_check_citation.py`)와 게이트 규칙 테스트(`test_gate_rules.py`) |
| `.github/workflows/tests.yml` | 처음 만드는 GitHub Actions 워크플로 |
| `design/ci.yml` | 함께 따라하기에서 설계하는 워크플로 |

```bash
uv sync
uv run pytest -v tests
```
