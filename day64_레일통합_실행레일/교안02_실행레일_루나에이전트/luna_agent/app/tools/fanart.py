"""도구 층: AI 팬아트 생성 도구(create_fanart)와 팬아트 기록(fanart_requests 표) 함수.

그림 한 장마다 비용이 드는 호출이다. 이 도구는 실행 전 검사(한 메시지 한 장, 하루 한도, 그림 요청 정책)를 통과한 호출에서만 실행된다.
생성한 그림의 검사(모더레이션, 브랜드 검사, 워터마크)와 기록은 실행 후 검사(guards/execution.py 의 check_fanart_image)가 한다.
팬이 쓴 문장은 그림 모델에 그대로 넘기지 않는다. 장면 다섯 칸만 뽑아 고정 안전 틀(visual.yaml 의 image_prompt)에 끼운다.
"""
import base64
import sqlite3
from uuid import uuid4

from langchain.tools import ToolRuntime, tool
from openai import AsyncOpenAI

from app.core.config import BASE_DATE, BASE_DATETIME, FANART_DIR, LUNA_IMAGE_PATH, llm
from app.core.policies import VISUAL
from app.core.prompts import IMAGE_PROMPT, SCENE_PROMPT
from app.core.schemas import AgentContext, FanartScene
from app.tools import fan_db

# 그림 프롬프트에 넣는 장면 칸(순서대로). 요약 칸(summary_ko)은 화면과 기록에만 쓰고 그림 프롬프트에 넣지 않는다
SCENE_SLOTS = ["place", "action", "season", "props", "mood"]

# 그림 생성과 모더레이션(guards/image_guards.py)이 같이 쓰는 OpenAI 클라이언트. 만들기만 하면 API 를 부르지 않는다
image_client = AsyncOpenAI()


# [보조 함수] 장면 뽑기
async def extract_scene(request: str) -> FanartScene:
    """팬아트 요청 문장에서 장면 다섯 칸과 한국어 요약을 뽑아 돌려준다(GPT 구조화 출력)."""
    scene_llm = llm.with_structured_output(FanartScene)
    return await scene_llm.ainvoke([("system", SCENE_PROMPT), ("human", request)])


# [보조 함수] 그림 생성
async def generate_image(prompt: str) -> bytes:
    """공식 설정 그림을 기준 이미지로 넘겨 새 그림 한 장을 만들고 PNG 바이트를 돌려준다(유료 호출)."""
    # 모델, 품질, 크기는 visual.yaml 의 generation 에서 읽는다(그림 정책 원본은 YAML 하나)
    generation = VISUAL["generation"]

    # images.edit 에 공식 그림을 넘겨야 얼굴, 머리색, 머리핀, 의상이 그림마다 같게 유지된다
    with open(LUNA_IMAGE_PATH, "rb") as reference:
        response = await image_client.images.edit(
            model=generation["model"], image=[reference], prompt=prompt,
            quality=generation["quality"], size=generation["size"],
        )
    return base64.b64decode(response.data[0].b64_json)


# [보조 함수] 오늘 만든 팬아트 수
def count_today_fanarts(fan_id: str, db_path) -> int:
    """기준일(BASE_DATE)에 이 팬이 만든(생성완료) 팬아트 수를 돌려준다. 막힌 요청은 세지 않는다."""
    rows = fan_db.fetch_all(
        "SELECT COUNT(*) AS used FROM fanart_requests WHERE fan_id = ? AND status = '생성완료' AND created_at LIKE ?",
        (fan_id, BASE_DATE + "%"),
        db_path,
    )
    return rows[0]["used"]


# [보조 함수] 팬아트 기록
def record_fanart_request(fan_id: str, summary: str, status: str, block_reason, db_path) -> str:
    """fanart_requests 표에 요청 한 건(생성완료 또는 차단)을 적고 요청 id(예: A0016)를 돌려준다."""
    rows = fan_db.fetch_all("SELECT MAX(request_id) AS last_id FROM fanart_requests", (), db_path)
    number = 0
    # 표가 비어 있으면 첫 id 가 A0001 이 된다
    if rows[0]["last_id"] is not None:
        number = int(rows[0]["last_id"][1:])
    request_id = f"A{number + 1:04d}"

    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO fanart_requests (request_id, fan_id, created_at, prompt_summary, status, block_reason) VALUES (?, ?, ?, ?, ?, ?)",
            (request_id, fan_id, BASE_DATETIME, summary, status, block_reason),
        )
        connection.commit()
    finally:
        connection.close()
    return request_id


# [도구] AI 팬아트 만들기
# content_and_artifact: 모델에게는 짧은 문장만, 그림 경로와 장면은 artifact 로 실행 후 검사와 화면에 넘긴다
@tool(response_format="content_and_artifact")
async def create_fanart(request: str, runtime: ToolRuntime[AgentContext]):
    """팬이 원하는 장면(예: 별빛 무대에서 응원봉 든 루나)으로 루나 팬아트 한 장을 만들어 돌려준다."""
    # 1. 요청에서 장면 칸만 뽑는다. 팬 문장을 그대로 그림 모델에 넘기지 않으려는 것이다
    scene = await extract_scene(request)
    values = scene.model_dump()

    # 2. 비지 않은 칸만 'place: ...; mood: ...' 꼴로 잇는다. 모두 비면 그릴 장면이 없어 다시 묻는다(scene_prompt 의 규칙)
    parts = []
    for name in SCENE_SLOTS:
        if values[name]:
            parts.append(f"{name}: {values[name]}")
    # 그릴 장면이 없음: 그림 API 를 부르지 않고 generated=False 로 돌려준다(실행 후 검사도 건너뛴다)
    if len(parts) == 0:
        return "어떤 장면을 그릴지 알 수 없어요. 무대나 계절 배경처럼 장면을 알려 달라고 해 주세요.", {"generated": False}

    # 3. 고정 안전 틀의 {scene} 자리에 장면을 끼워 그림을 만든다(유료)
    prompt = IMAGE_PROMPT.format(scene="; ".join(parts))
    image_bytes = await generate_image(prompt)

    # 4. 파일로 저장한다. 보여 줄지는 실행 후 검사가 정한다
    FANART_DIR.mkdir(parents=True, exist_ok=True)
    path = FANART_DIR / f"{runtime.context.fan_id}_{uuid4().hex[:8]}.png"
    path.write_bytes(image_bytes)
    return "팬아트를 만들었어요.", {"generated": True, "path": str(path), "summary": scene.summary_ko, "prompt": prompt}


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.tools.fanart
    # 그림은 만들지 않는다(유료). 프롬프트 조립과 오늘 사용 횟수만 확인한다
    from app.core.config import DB_PATH

    print("장면 칸:", SCENE_SLOTS)
    print("그림 프롬프트:", IMAGE_PROMPT.format(scene="place: a starlit concert stage; action: holding a lavender light stick; mood: cheerful"))
    print("기준일:", BASE_DATE, "/ F0006 오늘 만든 수:", count_today_fanarts("F0006", DB_PATH), "/ F0005:", count_today_fanarts("F0005", DB_PATH))
