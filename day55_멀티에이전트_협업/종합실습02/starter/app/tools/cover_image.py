"""도구 층: 커버 이미지를 만드는 함수. MCP 서버 없이 OpenAI 이미지 API 를 바로 부른다."""
import base64

from openai import AsyncOpenAI

from app.core.config import IMAGE_MODEL


async def generate_cover_image(prompt: str, path: str) -> str:
    """프롬프트로 만든 커버 이미지 1장을 path 에 PNG 로 저장하고 그 경로를 돌려준다."""
    # 유료 이미지 API 호출. 키는 환경변수 OPENAI_API_KEY 에서 읽는다.
    response = await AsyncOpenAI().images.generate(
        model=IMAGE_MODEL, prompt=prompt, n=1, size="1024x1024", quality="medium"
    )
    # 이미지는 base64 글자로 오므로 바이트로 풀어 파일로 쓴다.
    with open(path, "wb") as f:
        f.write(base64.b64decode(response.data[0].b64_json))
    return path
