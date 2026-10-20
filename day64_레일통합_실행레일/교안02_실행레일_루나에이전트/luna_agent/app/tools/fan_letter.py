"""도구 층: 루나에게 팬레터를 보내는 도구(send_fan_letter). 팬레터는 DB 에 미리 만들어 둔 fan_letters 표에 쌓인다.

함께 따라하기에서 완성하는 파일이다. 아직 에이전트에 붙이지 않았으므로 완성하기 전에도 앱과 테스트는 그대로 돈다.
- 보내는 사람(fan_id)은 모델이 정하지 않는다. 로그인 정보(runtime.context.fan_id)에서 읽으므로 남의 이름으로 보낼 자리가 없다.
- 글자 수, 링크, 연락처 확인은 도구 밖의 실행 레일(guards/execution.py 의 permission_problem)이 실행 전에 한다.
- 욕설, 비하 같은 내용은 이 도구까지 오기 전에 입력 레일(Jev 입력 정책)이 팬 메시지를 판정한다.
- 사람 승인은 받지 않는다. 돈이 나가지 않고 남의 데이터를 바꾸지 않는 낮은 위험 도구라, 승인을 붙이면 승인 피로만 늘어난다.
"""
import sqlite3

from langchain.tools import ToolRuntime, tool

from app.core.config import BASE_DATETIME
from app.core.schemas import AgentContext


# [도구] 루나에게 팬레터 보내기(위험도 낮음: 사람 승인 없이 실행된다)
@tool
def send_fan_letter(message: str, runtime: ToolRuntime[AgentContext]) -> dict:
    """로그인한 팬 본인의 이름으로 루나에게 팬레터 한 통(message)을 보내고 접수 결과를 돌려준다."""
    # TODO: 로그인한 팬 이름으로 팬레터 한 줄을 fan_letters 표에 넣고 접수 결과를 돌려준다
    # 1) sqlite3.connect(runtime.context.db_path) 로 연결을 연다(앱은 data/luna_fan.db, 평가와 테스트는 DB 사본 경로가 온다)
    # 2) SELECT MAX(letter_id) FROM fan_letters 로 마지막 id 를 읽어 다음 id 를 L0001, L0002 ... 모양으로 만든다(표가 비었으면 L0001)
    # 3) INSERT INTO fan_letters (letter_id, fan_id, message, sent_at, status) 로 한 줄 넣는다
    #    fan_id 는 runtime.context.fan_id, sent_at 은 BASE_DATETIME(수업 데이터의 기준 시각), status 는 '접수'
    # 4) commit 한 뒤 try/finally 로 연결을 꼭 닫는다
    # 5) {"letter_id": 만든 id, "result": "팬레터 접수"} 를 돌려준다
    raise NotImplementedError("TODO를 완성하세요")


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.tools.fan_letter
    # 원본 DB 를 고치지 않도록 도구 모양만 확인한다(완성 전에도 돈다. 쓰기는 수업이 끝난 뒤 강사가 공유하는 따라하기 정답의 tests/test_fan_letter.py 가 임시 사본으로 확인한다)
    print("도구 이름:", send_fan_letter.name)
    print("모델이 채우는 인자:", list(send_fan_letter.tool_call_schema.model_json_schema()["properties"]))
