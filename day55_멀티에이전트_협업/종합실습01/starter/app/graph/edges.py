"""그래프 층: 노드 사이의 갈 곳을 정하는 라우팅 함수. 여기서는 Send 로 병렬 분배한다."""
from langgraph.types import Send

from app.graph.state import TeamState


# [라우팅 함수] 분석 작업마다 data_analyst 로 Send 만들기
def dispatch(state: TeamState) -> list[Send] | str:
    """분석 작업마다 data_analyst 로 보내는 Send 목록을, 작업이 없으면 "supervisor" 를 돌려준다."""
    # TODO: 계획의 분석 작업마다 data_analyst 를 하나씩 병렬로 띄우는 Send 목록 만들기
    # 1) 계획(plan)이 비어 있으면 "supervisor" 를 돌려준다. 빈 리스트를 돌려주면 그래프가 조용히 끝난다
    # 2) 작업마다 data_analyst 로 가는 Send 를 만들어 리스트에 담는다. Send 에는 그 작업(task)과 산출물 폴더(run_dir)만 담는다
    # 3) Send 리스트를 돌려준다. 리스트 길이만큼 data_analyst 가 동시에 돈다
    raise NotImplementedError("TODO를 완성하세요")
