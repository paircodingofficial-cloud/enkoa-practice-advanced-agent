"""그래프 층: 바깥 그래프의 갈림길에서 다음 노드를 정하는 라우팅 함수. State 를 읽기만 하고 고치지 않는다."""
from app.core.prompts import RETRY_RULES
from app.graph.state import LunaState


# [라우팅 함수] 입력 레일 뒤
def route_after_input(state: LunaState) -> str:
    """입력 레일이 막았으면 "refuse", 통과했으면 "agent" 를 돌려준다."""
    # 막힘: 모델과 도구를 돌리지 않고 거절 노드로 간다
    if state["input_verdict"]["status"] == "blocked":
        return "refuse"
    # 통과: 에이전트 노드가 도구를 고르며 일한다
    return "agent"


# [라우팅 함수] 출력 레일 뒤
def route_after_output(state: LunaState) -> str:
    """다시 쓰면 고쳐질 규칙으로 막혔고 이번 턴에 아직 다시 쓰지 않았으면 "regenerate", 아니면 "end" 를 돌려준다."""
    verdict = state["output_verdict"]
    # 다시 쓰기: OUT-05, OUT-09 처럼 답을 쓰다 생긴 실수이고, 이번 턴에 처음 막혔을 때만 간다
    if verdict["status"] == "blocked" and verdict["rule_id"] in RETRY_RULES and state["retry_count"] == 0:
        return "regenerate"
    # 끝: 통과, 가림, 보안 규칙 막힘, 다시 쓴 답도 막힘. 막혔으면 출력 레일이 바꿔 둔 거절 문장으로 끝난다
    # 다시 쓰기를 한 번으로 묶어 답변 모델 비용이 끝없이 늘지 않는다
    return "end"


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.graph.edges
    print("입력 레일이 막았을 때:", route_after_input({"input_verdict": {"status": "blocked"}}))
    print("입력 레일을 지났을 때:", route_after_input({"input_verdict": {"status": "passed"}}))
    for rule_id in ["OUT-05", "OUT-09", "OUT-03"]:
        for retry_count in [0, 1]:
            state = {"output_verdict": {"status": "blocked", "rule_id": rule_id}, "retry_count": retry_count}
            print(f"{rule_id} 로 막힘, 다시 쓴 횟수 {retry_count} ->", route_after_output(state))
