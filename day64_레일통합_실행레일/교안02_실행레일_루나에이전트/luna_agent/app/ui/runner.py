"""화면 층: Streamlit 화면이 비동기 그래프를 부를 때 쓰는 '계속 살아 있는 이벤트 루프' 하나.

왜 필요한가:
- Streamlit 은 버튼을 누르거나 메시지를 보낼 때마다 화면 스크립트를 처음부터 다시 실행한다.
- 그때마다 asyncio.run 을 쓰면 실행마다 새 이벤트 루프가 생기고 끝나면 닫힌다.
- 그런데 판정 객체(NeMo LLMRails), 답변 모델(ChatOpenAI)의 HTTP 연결은 처음 쓴 루프에 묶인다.
  닫힌 루프에 묶인 객체를 다음 실행에서 다시 쓰면 "Event loop is closed" 오류가 난다.
- 그래서 루프 하나를 별도 스레드에서 계속 돌려 두고, 판정 객체를 만드는 일과 매 턴 실행을 모두 그 루프에 보낸다.
  (체크포인터의 SQLite 연결은 턴마다 그 루프 안에서 열고 닫는다)
"""
import asyncio
import threading


class BackgroundLoop:
    """별도 스레드에서 계속 도는 이벤트 루프. run(코루틴) 으로 일을 보내고 결과를 받는다."""

    def __init__(self):
        """새 이벤트 루프를 만들어 별도 스레드에서 돌리기 시작한다(돌려주는 값 없음)."""
        self.loop = asyncio.new_event_loop()
        # daemon=True: 화면 프로그램을 끄면 이 스레드도 함께 끝난다
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    # [보조 함수] 코루틴 하나 실행
    def run(self, coroutine):
        """코루틴을 살아 있는 루프에서 실행하고, 끝날 때까지 기다려 결과를 돌려준다."""
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        return future.result()


if __name__ == "__main__":
    # 해당 모듈 테스트: uv run -m app.ui.runner
    # 두 번 보낸 일이 같은 루프에서 도는지 확인한다(asyncio.run 이면 매번 다른 루프다)
    async def current_loop():
        """지금 도는 이벤트 루프 객체를 돌려준다."""
        return asyncio.get_running_loop()

    runner = BackgroundLoop()
    first = runner.run(current_loop())
    second = runner.run(current_loop())
    print("살아 있는 루프: 첫 실행과 두 번째 실행이 같은 루프인가?", first is second, "/ 닫혔나?", first.is_closed())
    closed_loop = asyncio.run(current_loop())
    print("asyncio.run: 같은 루프인가?", closed_loop is asyncio.run(current_loop()), "/ 끝난 루프가 닫혔나?", closed_loop.is_closed())
