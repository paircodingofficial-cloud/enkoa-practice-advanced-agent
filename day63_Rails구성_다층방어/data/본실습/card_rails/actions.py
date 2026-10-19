# 설정 폴더를 읽을 때 NeMo 가 @action 이 붙은 함수를 액션으로 등록합니다(노트북에서는 register_action)
import re

from nemoguardrails.actions import action

# 주민등록번호(앞 6자리-뒤 7자리)와 휴대전화 번호(010-0000-0000, 하이픈 생략 포함)
# (?<!\d)·(?!\d): 앞뒤가 숫자가 아닐 때만 맞춰 16자리 카드번호의 일부를 잘못 가리지 않게 합니다
RRN_PATTERN = re.compile(r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)")
PHONE_PATTERN = re.compile(r"(?<!\d)01[016789]-?\d{3,4}-?\d{4}(?!\d)")


@action(name="mask_pii")
async def mask_pii(text):
    """주민등록번호와 휴대전화 번호를 [주민등록번호]·[전화번호]로 바꾼 문자열을 돌려줍니다."""
    text = RRN_PATTERN.sub("[주민등록번호]", text)
    return PHONE_PATTERN.sub("[전화번호]", text)


# 고객 게시판 글에서 숨은 지시로 보는 패턴: 봇에게 내리는 안내나 공지 머리, 규칙보다 먼저 따르라는 말, 공식 도메인이 아닌 링크
INJECTION_PATTERNS = [
    re.compile(r"\[(시스템|운영|관리자) ?(안내|공지)"),
    re.compile(r"규칙보다"),
    re.compile(r"https?://(?!www\.hanbitcard\.example)"),
]


def has_hidden_instruction(chunk):
    """문서에 숨은 지시 패턴이 하나라도 있으면 True 를 돌려줍니다."""
    for pattern in INJECTION_PATTERNS:
        if pattern.search(chunk):
            return True
    return False


@action(name="filter_chunks")
async def filter_chunks(text):
    """고객 게시판 문서 가운데 숨은 지시 패턴이 있는 문서를 빼고, 남은 문서의 개인정보를 가린 검색 문서를 돌려줍니다."""
    kept = []

    # 검색 문서는 빈 줄로 나뉘고, 문서마다 "[출처: ...]" 머리가 붙어 있습니다
    for chunk in text.split("\n\n"):
        # 고객 누구나 쓰는 게시판 글만 패턴으로 검사합니다. 회사가 쓴 FAQ 와 상담 기록은 검사하지 않습니다
        if chunk.startswith("[출처: 고객 게시판]") and has_hidden_instruction(chunk):
            continue
        kept.append(await mask_pii(chunk))
    return "\n\n".join(kept)
