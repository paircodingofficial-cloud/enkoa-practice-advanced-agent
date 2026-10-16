# 연습 프로젝트에 Ruff 검사와 AI 리뷰 넣기: 작업 순서

부록 02 심화 노트북(`부록_02_GitHub_Actions_심화.ipynb`) 3절(Ruff 검사)과 4절(AI 코드 리뷰)을 실제 저장소에 적용하는 순서입니다. 워크플로 파일은 부록 02 기초 7절에서 만든 `.github/workflows/ci.yml` 하나에 넣습니다. 개념과 각 설정의 뜻은 노트북에 있습니다. 명령은 모두 `pytest_ci_practice` 폴더(저장소 최상위)에서 실행합니다.

먼저 작업 브랜치를 만듭니다.

```bash
git switch main
git pull
git switch -c add-ruff-ai-review
```

## 1. 라이브러리 설치

```bash
uv add --dev ruff
uv add langchain-core langchain-openai python-dotenv
```

`uv add`가 `pyproject.toml`과 `uv.lock`을 함께 고칩니다. 연습 프로젝트에는 이미 들어 있어 실행해도 파일이 바뀌지 않습니다.

이어서 `pyproject.toml` 맨 아래에 Ruff 설정을 붙여 넣습니다(연습 프로젝트에는 이미 있음).

```toml
[tool.ruff]
line-length = 120          # 한 줄 최대 길이

[tool.ruff.lint]
select = ["E", "F", "I"]   # E: 코드 스타일, F: 문법 오류·안 쓰는 import, I: import 순서
```

`uv run ruff check .`와 `uv run ruff format --check .`가 모두 통과하는지 확인합니다. 연습 프로젝트의 코드는 처음부터 통과합니다.

## 2. `ci.yml`에 Ruff 검사 단계 넣기

`unit-tests` 작업의 단계 맨 끝(`- name: 테스트` 단계 다음)에 넣습니다. 들여쓰기는 `- name: 테스트`와 같은 앞 여섯 칸입니다.

```yaml
      # [Ruff 추가] 코드 스타일 검사 단계. 라이브러리 설치 단계가 dev 묶음의 ruff 까지 설치해 두었음
      - name: 문법·스타일·import 순서 검사
        if: always()                              # 앞의 테스트가 실패해도 이 검사는 실행
        run: uv run ruff check .                  # pyproject.toml 의 select 규칙을 어긴 곳이 있으면 실패
      - name: 포맷 검사
        if: always()
        run: uv run ruff format --check .         # 다시 포맷해야 할 파일이 있으면 실패(파일은 바꾸지 않음)
```

## 3. AI 리뷰 넣기

### 3-1. 비밀 변수 등록

부록 02 기초 4-2와 같은 방법으로 등록합니다. 저장소 **Settings** > **Secrets and variables** > **Actions** > **New repository secret**에서 Name에 `OPENAI_API_KEY`, Secret에 키 값을 넣습니다. 댓글을 올릴 때 쓰는 `GH_TOKEN`은 GitHub가 실행마다 자동으로 주므로 등록하지 않습니다.

### 3-2. 내 컴퓨터에서 실행해 보기

리뷰 스크립트 `tools/ai_reviewer.py`는 연습 프로젝트에 들어 있습니다(코드 설명은 심화 4-2). 워크플로에 넣기 전에 먼저 돌려 봅니다.

1. 이 폴더에 `.env` 파일을 만들고 `OPENAI_API_KEY=키값` 한 줄을 적습니다. `.gitignore`가 막아 저장소에는 올라가지 않습니다.
2. 리뷰할 변경을 커밋합니다. 스크립트는 main과 비교해 커밋한 변경만 봅니다.
3. 비교할 main을 최신으로 받고 실행합니다.

   ```bash
   git fetch origin main
   uv run python tools/ai_reviewer.py
   ```

터미널에 리뷰가 출력되고 `review.md`로 저장되면 성공입니다. 바뀐 코드가 없으면 모델을 부르지 않고 `main 과 비교해 바뀐 코드가 없어 리뷰하지 않았습니다.`를 출력합니다. `Missing credentials`가 나오면 `.env`를, `Error code: 401`이 나오면 키 값을 확인합니다.

### 3-3. `ci.yml`에 `ai-review` 작업 넣기

파일 맨 아래(`gate-rules` 작업 다음)에 넣습니다. 들여쓰기는 `gate-rules:`와 같은 앞 두 칸입니다.

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
        run: uv sync --locked                     # uv.lock 에 적힌 버전 그대로 설치(langchain, python-dotenv 포함)
      - name: AI 리뷰 생성
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}   # 부록 02 기초 4-2 처럼 등록한 비밀 변수
        run: uv run python tools/ai_reviewer.py   # review.md 를 만듦
      - name: pull request 댓글로 올리기
        env:
          GH_TOKEN: ${{ github.token }}           # 실행마다 GitHub 가 주는 토큰. gh 명령이 이 값으로 로그인
        run: gh pr comment ${{ github.event.pull_request.number }} --body-file review.md
```

### 3-4. 올리고 확인

```bash
git add pyproject.toml uv.lock .github/workflows/ci.yml
git commit -m "Ruff 검사와 AI 코드 리뷰 추가"
git push -u origin add-ruff-ai-review
```

main으로 가는 pull request를 열면 `unit-tests` 두 검사의 단계 목록 끝에 `문법·스타일·import 순서 검사`와 `포맷 검사`가 보이고, `ai-review` 검사가 끝나면 리뷰 댓글이 달립니다. 실패와 통과를 직접 확인하는 방법은 심화 3-2입니다.

연습 프로젝트의 `design/ci.yml`에는 2절의 단계와 3-3의 작업이 이미 들어 있습니다(`[Ruff 추가]`, `[AI 리뷰 추가]` 주석). 기초 7절대로 이 파일을 복사했다면 2절과 3-3은 위치만 확인합니다.
