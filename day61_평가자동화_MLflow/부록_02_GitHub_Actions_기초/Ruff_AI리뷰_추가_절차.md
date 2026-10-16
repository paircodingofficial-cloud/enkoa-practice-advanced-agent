# 부록 02 연습 프로젝트에 Ruff와 AI 리뷰 추가하기

부록 02의 연습 프로젝트(`pytest_ci_practice/`)에 두 가지를 더하는 절차입니다. 노트북 8절(Ruff)과 9절(AI 리뷰)의 내용을 실제 작업 순서로 정리했습니다. 모든 명령은 `pytest_ci_practice` 폴더(저장소 최상위)에서 실행합니다.

- **Ruff**: 코드 스타일을 검사하고 정리하는 도구입니다. 예전에 따로 쓰던 Black(포맷 정리), isort(import 순서 정리), flake8(스타일·문법 규칙 검사)의 일을 하나로 합니다.
- **AI 리뷰**: pull request에서 바뀐 코드를 LLM이 읽고 리뷰를 댓글로 남깁니다.

두 가지 모두 새 워크플로 파일을 만들지 않고 기존 `.github/workflows/tests.yml`을 고칩니다. Ruff는 `pytest` 작업에 단계로 더하고, AI 리뷰는 권한과 실행 조건이 달라 `ai-review` 작업을 새로 더합니다.

## 1. 어디를 무엇으로 바꾸나

| 파일 | 바꾸는 내용 | 절 |
|---|---|---|
| `pyproject.toml` | `[dependency-groups]`의 `dev` 묶음에 `ruff` 추가 | 2-2 |
| `pyproject.toml` | `[tool.ruff]`, `[tool.ruff.lint]` 설정 추가 | 2-3 |
| `.github/workflows/tests.yml` | `pytest` 작업의 단계 끝에 Ruff 단계 두 개 추가 | 2-5 |
| `pyproject.toml` | `review` 묶음에 `langchain-core`, `langchain-openai` 추가 | 3-1 |
| `tools/ai_reviewer.py` | 새 파일: 바뀐 코드를 리뷰해 `review.md`로 저장 | 3-2 |
| `.gitignore` | `review.md` 추가 | 3-2 |
| `.github/workflows/tests.yml` | 맨 아래에 `ai-review` 작업 추가 | 3-5 |
| `uv.lock` | `uv add`가 자동으로 고침 | 2-2, 3-1 |

새로 받은 연습 프로젝트에는 `pyproject.toml`, `uv.lock`, `.gitignore`, `tools/ai_reviewer.py`가 이미 바뀌어 있고(코드도 Ruff 검사를 통과하게 정리되어 있음), 파일 안에 `[Ruff 추가]`, `[AI 리뷰 추가]` 주석으로 표시되어 있습니다. 이 경우 2-2, 2-3, 3-1, 3-2는 확인만 하고 넘어갑니다. `tests.yml`은 1~7절 실습 화면과 맞추려고 처음 모습 그대로 두었으므로 2-5, 3-5는 직접 고칩니다.

7절의 `design/ci.yml`에는 Ruff 단계(`unit-tests` 작업 끝)와 `ai-review` 작업이 이미 들어 있습니다. 7절대로 `ci.yml`로 바꿨다면 워크플로는 고치지 않고 3-3의 비밀 변수 등록만 하면 됩니다.

## 2. Ruff 추가

### 2-1. 작업 브랜치 만들기

```bash
git checkout main
git pull
git checkout -b add-ruff
```

### 2-2. Ruff 설치

```bash
uv add --dev ruff==0.17.1
uv run ruff --version
# ruff 0.17.1
```

`uv add` 한 줄이 `pyproject.toml`과 `uv.lock`을 함께 고칩니다. `pyproject.toml` 맨 아래에 아래 묶음이 생깁니다. `dev` 묶음은 `uv sync`가 기본으로 함께 설치하므로, `tests.yml`의 `라이브러리 설치` 단계(`uv sync --locked`)가 Ruff까지 설치합니다.

```toml
[dependency-groups]
dev = [
    "ruff==0.17.1",
]
```

### 2-3. Ruff 설정 추가

`pyproject.toml` 맨 아래에 붙여 넣습니다. 이 설정은 `uv.lock`을 바꾸지 않습니다.

```toml
[tool.ruff]
line-length = 120          # 한 줄 최대 길이. ruff format 이 줄을 나누는 기준이자 E501(줄이 너무 김) 검사 기준

[tool.ruff.lint]
# 검사할 규칙 묶음: E 는 코드 스타일(flake8 의 pycodestyle), F 는 문법 오류·안 쓰는 import(flake8 의 Pyflakes),
# I 는 import 순서(isort)입니다.
select = ["E", "F", "I"]
```

### 2-4. 로컬에서 검사하고 고치기

```bash
uv run ruff check .
# All checks passed!

uv run ruff format --check .
# 7 files already formatted

uv run pytest -q tests
# 13 passed
```

연습 프로젝트는 두 검사를 모두 통과합니다. 코드를 고친 뒤 검사가 실패하면 `uv run ruff check --fix .`와 `uv run ruff format .`으로 고치고 다시 검사합니다.

### 2-5. `tests.yml`의 `pytest` 작업에 Ruff 단계 추가

`tests.yml`의 마지막 단계가 `테스트`이므로, 파일 맨 끝에 아래 단계를 붙이면 `pytest` 작업의 단계 끝에 들어갑니다. `- name: 테스트`와 같은 들여쓰기(앞 여섯 칸)로 맞춥니다.

```yaml
      # [Ruff 추가] 코드 스타일 검사 단계. 라이브러리 설치 단계가 dev 묶음의 ruff 까지 설치해 두었음
      - name: 문법·스타일·import 순서 검사
        if: always()                              # 앞의 테스트가 실패해도 이 검사는 실행
        run: uv run ruff check .                  # pyproject.toml 의 select 규칙을 어긴 곳이 있으면 실패
      - name: 포맷 검사
        if: always()
        run: uv run ruff format --check .         # 다시 포맷해야 할 파일이 있으면 실패(파일은 바꾸지 않음)
```

- **새 작업이 아니라 단계로 넣는 이유**: 작업(job)마다 GitHub가 새 러너를 빌려 저장소 받기, uv 설치, 라이브러리 설치를 처음부터 다시 합니다. Ruff는 `pytest` 작업과 권한·실행 조건이 같아서 한 작업에 모으면 준비를 한 번만 합니다.
- **`if: always()`**: 한 작업 안에서는 앞 단계가 실패하면 뒤 단계를 건너뜁니다. 테스트가 실패해도 Ruff 검사 결과를 보도록 붙였습니다.

### 2-6. 올리고 pull request 열기

```bash
git add pyproject.toml uv.lock .github/workflows/tests.yml tests/
git commit -m "Ruff 코드 스타일 검사 추가"
git push -u origin add-ruff
```

pull request의 `pytest` 검사를 열면 단계 목록 끝에 `문법·스타일·import 순서 검사`와 `포맷 검사`가 보입니다. 둘 중 하나라도 실패하면 `pytest` 검사가 실패로 표시되므로, 6절에서 `pytest`를 필수 검사로 넣었다면 병합도 막힙니다.

## 3. AI 리뷰 추가

### 3-1. LangChain 설치(`review` 묶음)

```bash
uv add --group review langchain-core==1.6.5 langchain-openai==1.3.5
```

`pyproject.toml`의 `[dependency-groups]`에 `review` 묶음이 생기고 `uv.lock`이 함께 고쳐집니다. `review` 묶음은 기본 설치에서 빠지므로 `pytest` 작업의 설치는 그대로이고, `uv sync --group review`나 `uv run --group review`일 때만 설치됩니다.

```toml
review = [
    "langchain-core==1.6.5",
    "langchain-openai==1.3.5",
]
```

### 3-2. 리뷰 스크립트 만들기

워크플로가 실행하는 보조 스크립트이므로 `tools/` 폴더에 둡니다. 스크립트가 만드는 `review.md`는 저장소에 올리지 않도록 `.gitignore`에 `review.md` 한 줄을 더합니다.

`tools/ai_reviewer.py`

```python
"""pull request 에서 바뀐 코드(git diff)를 LLM 에게 보여 주고 받은 리뷰를 review.md 로 저장합니다.

GitHub Actions 의 tests 워크플로(ai-review 작업)가 실행하고, review.md 를 pull request 댓글로 올립니다.
로컬 실행(pytest_ci_practice 폴더에서, OPENAI_API_KEY 필요):
    git fetch origin main
    uv run --group review python tools/ai_reviewer.py
"""

import subprocess
from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# main 과 갈라진 지점부터 지금까지 이 브랜치에서 바뀐 부분만 가져옵니다(main 에 새로 생긴 커밋은 빠집니다).
diff = subprocess.run(["git", "diff", "origin/main...HEAD"], capture_output=True, text=True, check=True).stdout

if diff.strip() == "":
    review = "main 과 비교해 바뀐 코드가 없어 리뷰하지 않았습니다."
else:
    # 너무 긴 변경은 앞부분 10000자만 보내 모델 입력 길이와 비용을 줄입니다.
    diff = diff[:10000]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "당신은 시니어 파이썬 개발자입니다. 코드 변경(diff)을 읽고 잠재적인 버그와 스타일 문제를 짚고, "
                "잘한 점도 적어 주세요. 한국어 마크다운으로 간결하게 씁니다.",
            ),
            ("human", "다음 코드 변경을 리뷰해 주세요.\n\n```diff\n{diff}\n```"),
        ]
    )
    llm = ChatOpenAI(model="gpt-4.1")
    review = (prompt | llm).invoke({"diff": diff}).content

# 워크플로의 다음 단계가 이 파일을 pull request 댓글로 올립니다.
Path("review.md").write_text(review, encoding="utf-8")
print(review)
```

- `origin/main...HEAD`(점 세 개)는 main과 갈라진 지점부터 이 브랜치에서 바뀐 부분만 보여 줍니다.
- 바뀐 코드가 없으면 모델을 부르지 않고, 너무 긴 변경은 앞부분 10000자만 보냅니다.

로컬에서 먼저 돌려 볼 수 있습니다(`OPENAI_API_KEY` 환경변수 필요).

```bash
git fetch origin main
uv run --group review python tools/ai_reviewer.py
```

### 3-3. 비밀 변수 `OPENAI_API_KEY` 등록

저장소 **Settings** > **Secrets and variables** > **Actions** > **New repository secret**에서 Name에 `OPENAI_API_KEY`, Secret에 키 값을 넣고 **Add secret**을 누릅니다. 워크플로에서는 `${{ secrets.OPENAI_API_KEY }}`로 읽으며, 로그에는 `***`로 가려집니다.

### 3-4. `github.token`: 발급·등록이 필요 없는 토큰

댓글 단계의 `GH_TOKEN: ${{ github.token }}`은 GitHub가 작업마다 자동으로 만들고 작업이 끝나면 만료되는 토큰입니다. 따로 발급하거나 등록하지 않으며, `gh` 명령이 환경변수 `GH_TOKEN`으로 로그인하기 때문에 이 값을 넘깁니다.

할 일은 권한 주기 하나입니다. `ai-review` 작업의 `permissions:`에 `pull-requests: write`를 적습니다(3-5에 들어 있음). 저장소 기본 권한 설정은 바꾸지 않아도 됩니다.

포크에서 온 pull request는 읽기 전용 토큰만 받고 비밀 변수도 받지 못해 AI 리뷰가 실패합니다.

### 3-5. `tests.yml`에 `ai-review` 작업 추가

`.github/workflows/tests.yml`의 맨 아래(2-5에서 붙인 Ruff 단계 다음)에 붙여 넣습니다. 이번에는 작업이므로 `pytest:`와 같은 들여쓰기(앞 두 칸)로 맞춥니다.

```yaml
  # [AI 리뷰 추가] pull request 에서 바뀐 코드를 LLM 이 리뷰해 댓글로 남기는 작업. 비밀 변수 OPENAI_API_KEY 필요
  ai-review:
    if: github.event_name == 'pull_request'      # push·직접 실행에서는 건너뜀(리뷰할 pull request 가 없음)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      pull-requests: write                        # 리뷰를 pull request 댓글로 올리려면 필요
    steps:
      - name: 저장소 받기
        uses: actions/checkout@v7
        with:
          fetch-depth: 0                          # 모든 커밋을 받아야 origin/main 과 비교 가능(기본 1은 마지막 커밋만)
      - name: uv 설치
        uses: astral-sh/setup-uv@v10.2.0
        with:
          python-version: "3.12"
      - name: 라이브러리 설치
        run: uv sync --locked --group review      # 기본 묶음에 review 묶음(langchain)까지 설치
      - name: AI 리뷰 생성
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}   # 4-2 처럼 등록한 비밀 변수
        run: uv run python tools/ai_reviewer.py   # review.md 를 만듦
      - name: pull request 댓글로 올리기
        env:
          GH_TOKEN: ${{ github.token }}           # 실행마다 GitHub 가 주는 토큰. gh 명령이 이 값으로 로그인
        run: gh pr comment ${{ github.event.pull_request.number }} --body-file review.md
```

- **새 작업으로 두는 이유**: 이 작업만 pull request 쓰기 권한, 비밀 변수, pull request일 때만 도는 조건이 필요합니다. `pytest` 작업과 나누어 권한을 이 작업에만 줍니다.
- `if`: main에 올릴 때와 직접 실행할 때는 리뷰할 pull request가 없으므로 이 작업을 건너뜁니다.
- `fetch-depth: 0`: 모든 커밋을 받아야 `origin/main`과 비교할 수 있습니다.

### 3-6. 올리고 pull request 열기

```bash
git add pyproject.toml uv.lock .gitignore tools/ai_reviewer.py .github/workflows/tests.yml
git commit -m "AI 코드 리뷰 작업 추가"
git push
```

pull request를 열면 검사 영역에 `pytest`와 나란히 `ai-review` 검사가 돌고, 끝나면 리뷰 댓글이 달립니다. 참고 의견이므로 필수 검사에는 넣지 않습니다. pull request마다 API를 한 번 부르므로 비용이 듭니다.

## 4. 다 고친 `tests.yml`

2-5와 3-5를 마친 `.github/workflows/tests.yml` 전체입니다.

```yaml
name: tests                                       # Actions 탭과 검사 영역에 보일 워크플로 이름

on:                                               # 이 워크플로를 실행할 이벤트
  push:                                           # 브랜치에 커밋을 올릴 때
    branches: [main]                              # 그중 main 브랜치에 올릴 때만
  pull_request:                                   # pull request를 열거나 커밋을 더할 때
  workflow_dispatch:                              # Actions 탭의 Run workflow 버튼을 누를 때

jobs:                                             # 할 작업 목록(작업마다 새 러너에서 따로 실행)
  pytest:                                         # 작업 이름. 실행 화면과 검사 영역에 이 이름으로 보임
    runs-on: ubuntu-latest                        # 러너: GitHub가 빌려주는 최신 우분투 가상 컴퓨터
    timeout-minutes: 10                           # 10분이 지나도 안 끝나면 작업을 멈춤
    steps:                                        # 차례로 실행할 단계(앞 단계가 실패하면 뒤는 건너뜀)
      - name: 저장소 받기                         # 단계 이름. 실행 로그에 이 이름으로 보임
        uses: actions/checkout@v7                 # 남이 만든 액션 실행: 저장소 코드를 러너로 내려받음
      - name: uv 설치
        uses: astral-sh/setup-uv@v10.2.0          # 남이 만든 액션 실행: 러너에 uv 설치(@ 뒤는 버전)
        with:                                     # 액션에 넘기는 값(받는 값은 액션 README에 있음)
          python-version: "3.12"                  # uv가 쓸 파이썬 버전
      - name: 라이브러리 설치
        run: uv sync --locked                     # 명령 실행: uv.lock에 적힌 버전 그대로 설치
      - name: 비밀 변수 확인
        env:                                      # 이 단계에서만 쓰는 환경변수
          DEMO_TOKEN: ${{ secrets.DEMO_TOKEN }}   # 등록한 비밀 변수의 값(4-2에서 등록)
        run: |                                    # | 다음 줄부터 들여 쓴 여러 줄을 차례로 실행
          echo "DEMO_TOKEN 값: $DEMO_TOKEN"
          echo "DEMO_TOKEN 길이: ${#DEMO_TOKEN}"  # ${#변수}는 셸에서 값의 글자 수
      - name: 테스트
        run: uv run pytest -v tests               # 명령 실행: 테스트. 하나라도 실패하면 작업 실패
      # [Ruff 추가] 코드 스타일 검사 단계. 라이브러리 설치 단계가 dev 묶음의 ruff 까지 설치해 두었음
      - name: 문법·스타일·import 순서 검사
        if: always()                              # 앞의 테스트가 실패해도 이 검사는 실행
        run: uv run ruff check .                  # pyproject.toml 의 select 규칙을 어긴 곳이 있으면 실패
      - name: 포맷 검사
        if: always()
        run: uv run ruff format --check .         # 다시 포맷해야 할 파일이 있으면 실패(파일은 바꾸지 않음)

  # [AI 리뷰 추가] pull request 에서 바뀐 코드를 LLM 이 리뷰해 댓글로 남기는 작업. 비밀 변수 OPENAI_API_KEY 필요
  ai-review:
    if: github.event_name == 'pull_request'      # push·직접 실행에서는 건너뜀(리뷰할 pull request 가 없음)
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      pull-requests: write                        # 리뷰를 pull request 댓글로 올리려면 필요
    steps:
      - name: 저장소 받기
        uses: actions/checkout@v7
        with:
          fetch-depth: 0                          # 모든 커밋을 받아야 origin/main 과 비교 가능(기본 1은 마지막 커밋만)
      - name: uv 설치
        uses: astral-sh/setup-uv@v10.2.0
        with:
          python-version: "3.12"
      - name: 라이브러리 설치
        run: uv sync --locked --group review      # 기본 묶음에 review 묶음(langchain)까지 설치
      - name: AI 리뷰 생성
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}   # 4-2 처럼 등록한 비밀 변수
        run: uv run python tools/ai_reviewer.py   # review.md 를 만듦
      - name: pull request 댓글로 올리기
        env:
          GH_TOKEN: ${{ github.token }}           # 실행마다 GitHub 가 주는 토큰. gh 명령이 이 값으로 로그인
        run: gh pr comment ${{ github.event.pull_request.number }} --body-file review.md
```

## 5. 자주 나는 실패

| 증상 | 원인 | 해결 |
|---|---|---|
| `라이브러리 설치` 단계에서 ``The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.`` | `uv.lock`을 커밋하지 않았거나 `pyproject.toml`만 손으로 고침 | 로컬에서 `uv lock`을 실행하고 `uv.lock`을 함께 커밋 |
| `pytest` 작업의 `포맷 검사` 단계 실패 | 포맷하지 않은 파일을 올림 | 로컬에서 `uv run ruff format .` 후 다시 커밋 |
| `pytest` 작업에서 `F401`(안 쓰는 import), `I001`(import 순서) | 규칙 위반 | `uv run ruff check --fix .` 후 다시 커밋 |
| 붙여 넣은 뒤 워크플로가 아예 안 돔(Actions 탭에 문법 오류 표시) | 들여쓰기가 어긋남 | Ruff 단계는 앞 여섯 칸(`- name: 테스트`와 같게), `ai-review:`는 앞 두 칸(`pytest:`와 같게) |
| `AI 리뷰 생성` 단계에서 `AuthenticationError` | `OPENAI_API_KEY`가 없거나 틀림. 포크에서 온 pull request에는 비밀 변수가 전달되지 않음 | 3-3대로 등록, 포크 pull request는 저장소 안 브랜치로 다시 올림 |
| 댓글 단계에서 `Resource not accessible by integration` 같은 권한 오류 | `ai-review` 작업에 `pull-requests: write`가 없음 | 3-5의 `permissions`를 그대로 붙였는지 확인 |
