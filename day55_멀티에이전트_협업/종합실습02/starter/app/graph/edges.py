"""그래프 층: 노드 사이의 갈 곳을 정하는 라우팅 함수. 여기서는 Send 로 병렬 분배한다."""
from langgraph.types import Send

from app.graph.state import State


# [라우팅 함수] 새 작업마다 researcher 로 Send 만들기
def dispatch(state: State) -> list[Send] | str:
    """새 작업마다 researcher 로 보내는 Send 목록을, 새 작업이 없으면 "synthesizer" 를 돌려준다."""
    # TODO: 계획의 작업마다 researcher 를 하나씩 병렬로 띄우는 Send 목록 만들기
    # 1) state["plan"] 을 돌며 state["findings"] 에 task_id 가 아직 없는 작업만 todo 에 담는다(보충 조사 때 끝난 작업을 다시 조사하지 않게)
    # 2) 보낼 작업이 하나도 없으면 "synthesizer" 를 돌려준다. 빈 리스트를 돌려주면 그래프가 조용히 끝난다
    # 3) 작업마다 researcher 로 가는 Send 를 만들어 리스트로 돌려준다. Send 에는 그 작업(task)만 담는다. 리스트 길이만큼 researcher 가 동시에 돈다
    raise NotImplementedError("TODO를 완성하세요")
