"""함께 따라하기: 도서관 안내 챗봇 코드(rag_answer.py)의 테스트를 씁니다.

같은 확인을 fixture·parametrize 없이 한 번, 쓰고 한 번 작성해 두 방식을 비교합니다.
LLM 은 부르지 않습니다. 모델 자리에는 LangChain 이 테스트용으로 제공하는 가짜 모델 FakeListChatModel 을 넣어,
"모델이 이렇게 답했다면" 우리 코드가 어떻게 처리하는지 확인합니다.
실행 방법(부록_01_pytest_기초 폴더에서): uv run pytest -v tests/test_followalong.py
"""
import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from rag_answer import ABSTAIN, answer_question, format_documents

QUESTION = "일반 도서는 몇 권까지 빌릴 수 있나요?"
# format_documents 가 문서 두 개로 만들어야 할 문맥입니다.
EXPECTED_CONTEXT = ("[loan-basic] 회원은 일반 도서를 1인 7권까지 14일 동안 빌릴 수 있습니다.\n\n"
                    "[loan-extension] 빌린 도서는 1회에 한해 7일 연장할 수 있습니다.")

# 가짜 모델이 돌려줄 답입니다. 검색한 문서는 loan-basic, loan-extension 두 개이고, loan-weekend 는 검색하지 않은 문서입니다.
# 앞의 둘은 검색한 문서만 인용했고, 뒤의 둘은 검색하지 않은 문서를 인용했습니다.
CITED = "일반 도서는 1인 7권까지 14일 동안 빌릴 수 있습니다. [loan-basic]"
TWO_CITED = "일반 도서는 14일 동안 빌리고 1회 7일 연장할 수 있습니다. [loan-basic] [loan-extension]"
UNKNOWN_ID = "주말에는 3일 더 빌릴 수 있습니다. [loan-weekend]"
MIXED = "일반 도서는 14일 동안 빌리고 주말에는 3일 더 빌릴 수 있습니다. [loan-basic] [loan-weekend]"


# 1-1. [fixture 없이] format_documents 가 문서 두 개로 EXPECTED_CONTEXT 를 만드는지 확인하는 테스트
#      - 테스트 안에서 Document 두 개를 직접 만들어 docs 목록에 담습니다.
#        Document(page_content="회원은 일반 도서를 1인 7권까지 14일 동안 빌릴 수 있습니다.", metadata={"source_id": "loan-basic"})
#        Document(page_content="빌린 도서는 1회에 한해 7일 연장할 수 있습니다.", metadata={"source_id": "loan-extension"})
#      - format_documents(docs) 가 EXPECTED_CONTEXT 와 같은지 assert 합니다.
def test_format_documents_plain():
    pytest.fail("이 테스트를 작성하세요")


# 1-2. [fixture 만들기] 1-1의 문서 두 개를 돌려주는 fixture
#      - 지금은 빈 목록을 돌려줘서 docs 를 쓰는 테스트가 실패합니다.
#      - 1-1에서 만든 Document 두 개를 담은 목록을 돌려주도록 고칩니다.
@pytest.fixture
def docs():
    return []


# 1-3. [fixture 쓰기] 1-1과 같은 확인을, 문서를 인자 docs 로 받아서 하는 테스트
#      - 문서를 만드는 코드 없이 assert 한 줄만 씁니다.
def test_format_documents_with_fixture(docs):
    pytest.fail("이 테스트를 작성하세요")


# 2-1. [parametrize 없이] answer_question 의 인용 확인이 근거 있는 답은 통과시키고, 지어낸 인용은 막는지 확인하는 테스트
#      - 가짜 모델 FakeListChatModel(responses=[답]) 은 불리면 그 답을 돌려줍니다. 모델이 그렇게 답한 상황을 만드는 것입니다.
#      - 두 경우를 한 함수 안에서 차례로 확인합니다.
#        모델 답이 CITED 이면 answer_question(QUESTION, docs, 가짜 모델) 결과가 CITED 그대로인지
#        모델 답이 UNKNOWN_ID(검색하지 않은 loan-weekend 인용)이면 결과가 ABSTAIN 인지
def test_citation_guard_plain(docs):
    pytest.fail("이 테스트를 작성하세요")


# 2-2. [parametrize 쓰기] 같은 확인을 모델 답 네 가지로 하나씩 따로 판정하는 테스트
#      - 함수 위에 아래 parametrize 를 붙이고, 인자를 (docs, reply, expected) 로 고칩니다.
#        @pytest.mark.parametrize(
#            "reply, expected",
#            [(CITED, CITED), (TWO_CITED, TWO_CITED), (UNKNOWN_ID, ABSTAIN), (MIXED, ABSTAIN)],
#            ids=["cited", "two_cited", "unknown_id", "mixed"],
#        )
#      - 모델 답이 reply 일 때 answer_question 결과가 expected 인지 assert 한 줄로 확인합니다.
def test_citation_guard(docs):
    pytest.fail("이 테스트를 작성하세요")

