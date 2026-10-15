"""답변의 인용을 원문과 대조하는 함수입니다. 교안 01의 normalize, check_citation 과 같습니다.

테스트할 코드라 직접 실행하지 않습니다. 이 파일의 테스트는 tests/ 에 있습니다.
실행 방법(pytest_ci_practice 폴더에서): uv run pytest -v tests
"""


def normalize(text):
    """뜻과 상관없는 표기 차이(가운뎃점 모양, 줄바꿈, 연속 공백)를 하나로 맞춥니다."""
    for mark in ["･", "∙", "・", "•"]:
        text = text.replace(mark, "·")
    # split 은 줄바꿈·탭·연속 공백에서 모두 나누므로, 공백 하나로 다시 이으면 공백이 통일됩니다.
    return " ".join(text.split())


def check_citation(citation, source_texts, searched_ids):
    """인용 하나가 이번 답변의 실제 근거인지 차례로 검사해, 처음 걸린 문제 또는 "확인"을 돌려줍니다.

    citation: 답변 부분에 붙은 인용 하나입니다. {"evidence_id": 근거 ID, "quote": 인용 구절}
    source_texts: 근거 ID -> 문서 원문 사전입니다.
    searched_ids: 이번 질문에서 검색해 온 문서의 근거 ID 목록입니다.
    반환값: 아래 순서로 검사해 처음 걸린 문제를 돌려줍니다. 모두 통과하면 "확인"입니다.
        "없는 근거 ID": 문서에 없는 근거 ID 를 인용함
        "검색하지 않은 문서": 있는 문서지만 이번 질문에서 검색하지 않음
        "원문에 없는 문구": 표기를 맞춘(normalize) 뒤에도 인용 구절이 원문에 없음
    """
    cited_id = citation["evidence_id"]
    if cited_id not in source_texts:
        return "없는 근거 ID"
    if cited_id not in searched_ids:
        return "검색하지 않은 문서"
    if normalize(citation["quote"]) not in normalize(source_texts[cited_id]):
        return "원문에 없는 문구"
    return "확인"
