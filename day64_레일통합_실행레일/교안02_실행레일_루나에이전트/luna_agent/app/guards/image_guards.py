"""가드 층: 만든 팬아트 그림을 팬에게 보여 주기 전에 검사하고 표시를 찍는다.

1. moderate_image: OpenAI 모더레이션(이미지 입력)으로 선정성, 폭력, 자해 점수를 보고 visual.yaml 기준값과 비교한다.
2. brand_check: 비전 LLM 이 공식 설정 그림과 만든 그림을 함께 보고 브랜드 검사 질문(BRD-01~05)에 yes, no 로 답한다.
   모더레이션은 실존 인물, 그림 속 글자, 다른 회사 캐릭터를 보지 못해서 브랜드 검사를 함께 둔다.
3. stamp_watermark: 검사를 통과한 그림 오른쪽 아래에 'AI 생성 팬아트' 를 찍는다(AI 생성물 표시).
"""
import base64
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from PIL import Image, ImageDraw, ImageFont

from app.core.config import BRAND_CHECK_MODEL, FONT_CANDIDATES, LUNA_IMAGE_PATH
from app.core.policies import VISUAL
from app.core.prompts import BRAND_CHECK_PROMPT
from app.core.schemas import BrandCheck
from app.tools.fanart import image_client

# 브랜드 검사 비전 모델. 만들기만 하면 API 를 부르지 않는다
brand_llm = ChatOpenAI(model=BRAND_CHECK_MODEL)


# [보조 함수] 그림을 data 주소로
def image_data_url(path) -> str:
    """PNG 파일을 모델에 넘길 수 있는 data 주소(data:image/png;base64,...)로 돌려준다."""
    encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# [보조 함수] 모더레이션 점수 받기
async def moderation_scores(path) -> dict:
    """그림 한 장의 모더레이션 범주별 점수 {범주 이름: 0~1} 를 돌려준다(OpenAI 모더레이션 호출)."""
    response = await image_client.moderations.create(
        model=VISUAL["moderation"]["model"],
        input=[{"type": "image_url", "image_url": {"url": image_data_url(path)}}],
    )
    # by_alias=True: 범주 이름을 visual.yaml 과 같은 모양(violence/graphic, self-harm)으로 받는다
    return response.results[0].category_scores.model_dump(by_alias=True)


# [가드] 모더레이션 검사
async def moderate_image(path) -> dict:
    """{"passed", "rule_id", "scores"} 를 돌려준다. 기준값 이상인 범주가 있으면 passed 가 False, rule_id 는 MOD-범주 이름이다."""
    moderation = VISUAL["moderation"]
    scores = await moderation_scores(path)

    # 범주마다 기준값과 비교한다. sexual 처럼 따로 정한 범주는 더 엄격한 값을 쓴다
    checked = {}
    for category in moderation["categories"]:
        threshold = moderation["threshold"]
        if category in moderation["category_thresholds"]:
            threshold = moderation["category_thresholds"][category]
        checked[category] = scores[category]
        # 기준값 이상인 첫 범주에서 바로 실패로 돌려준다
        if scores[category] >= threshold:
            return {"passed": False, "rule_id": "MOD-" + category, "scores": checked}
    # 모든 범주가 기준값 아래: 통과
    return {"passed": True, "rule_id": "", "scores": checked}


# [보조 함수] 브랜드 검사 답 받기
async def ask_brand_check(path) -> BrandCheck:
    """공식 그림과 만든 그림을 비전 LLM 에 함께 넘겨 받은 브랜드 검사 답(BrandCheck)을 돌려준다."""
    # 첫 번째 그림이 공식 설정 그림, 두 번째가 만든 그림이라고 질문지에 적혀 있으므로 순서를 지킨다
    message = HumanMessage(content=[
        {"type": "text", "text": BRAND_CHECK_PROMPT},
        {"type": "image_url", "image_url": {"url": image_data_url(LUNA_IMAGE_PATH)}},
        {"type": "image_url", "image_url": {"url": image_data_url(path)}},
    ])
    return await brand_llm.with_structured_output(BrandCheck).ainvoke([message])


# [가드] 브랜드 검사
async def brand_check(path) -> dict:
    """{"passed", "rule_id", "answers"} 를 돌려준다. 실패로 보는 답(visual.yaml 의 brand_fail_if)이 하나라도 나오면 passed 가 False 다."""
    result = await ask_brand_check(path)
    answers = {}
    for item in result.answers:
        answers[item.check_id] = item.answer

    # 질문마다 실패 답과 비교한다. 모델이 답하지 않은 질문도 확인하지 못했으므로 실패로 본다
    for check_id, fail_answer in VISUAL["brand_fail_if"].items():
        if check_id not in answers:
            return {"passed": False, "rule_id": check_id, "answers": answers}
        # 실패로 보는 답이 나온 질문: 그 질문 id(BRD-..)로 실패
        if answers[check_id] == fail_answer:
            return {"passed": False, "rule_id": check_id, "answers": answers}
    # 모든 질문이 실패 답이 아님: 통과
    return {"passed": True, "rule_id": "", "answers": answers}


# [보조 함수] 한글 글꼴 찾기
def load_font(size: int):
    """FONT_CANDIDATES 가운데 있는 첫 한글 글꼴을 돌려준다. 없으면 기본 글꼴(한글이 네모로 보일 수 있음)이다."""
    for font_path in FONT_CANDIDATES:
        # 이 컴퓨터에 있는 첫 글꼴 파일을 쓴다
        if Path(font_path).exists():
            return ImageFont.truetype(font_path, size)
    # 후보가 하나도 없음: Pillow 기본 글꼴
    return ImageFont.load_default(size=size)


# [가드] 워터마크
def stamp_watermark(path) -> None:
    """그림 오른쪽 아래에 반투명 띠와 'AI 생성 팬아트' 글자를 찍어 같은 파일에 저장한다."""
    image = Image.open(path).convert("RGBA")
    text = VISUAL["generation"]["watermark_text"]
    font = load_font(max(18, image.width // 28))

    # 글자 크기를 재서 오른쪽 아래 여백 안에 띠 자리를 정한다
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    margin = image.width // 40
    x = image.width - (right - left) - margin * 2
    y = image.height - (bottom - top) - margin * 2

    # 어떤 배경에서도 읽히게 검은 반투명 띠 위에 흰 글자를 쓴다
    draw.rectangle([x - margin // 2, y - margin // 2, image.width - margin, image.height - margin], fill=(0, 0, 0, 120))
    draw.text((x, y - top), text, font=font, fill=(255, 255, 255, 235))
    Image.alpha_composite(image, overlay).convert("RGB").save(path)


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.guards.image_guards
    # 모더레이션과 브랜드 검사는 유료라 부르지 않는다. 기준값, 질문지, 워터마크만 확인한다
    from app.core.config import OUTPUT_DIR

    print("모더레이션 기준:", VISUAL["moderation"]["threshold"], VISUAL["moderation"]["category_thresholds"])
    print("브랜드 검사 실패 답:", VISUAL["brand_fail_if"])
    print(BRAND_CHECK_PROMPT[:200])
    sample_path = OUTPUT_DIR / "watermark_sample.png"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Image.open(LUNA_IMAGE_PATH).convert("RGB").resize((512, 768)).save(sample_path)
    stamp_watermark(sample_path)
    print("워터마크 예시 저장:", sample_path)
