"""pull request 에서 바뀐 코드(git diff)를 LLM 에게 보여 주고 받은 리뷰를 review.md 로 저장합니다.

GitHub Actions 의 ci 워크플로(ai-review 작업)가 실행하고, review.md 를 pull request 댓글로 올립니다.
로컬 실행(pytest_ci_practice 폴더에서, .env 에 OPENAI_API_KEY 필요):
    git fetch origin main
    uv run python tools/ai_reviewer.py
"""

import subprocess
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 내 컴퓨터에서는 .env 의 OPENAI_API_KEY 를 읽습니다. CI 에서는 워크플로가 비밀 변수를 환경변수로 넘겨 주고,
# load_dotenv 는 이미 있는 환경변수를 덮어쓰지 않으므로 .env 가 없어도 그대로 동작합니다.
load_dotenv(find_dotenv(usecwd=True))

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
