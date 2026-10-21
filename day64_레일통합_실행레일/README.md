# 가드레일 통합과 실행 레일: 루나 팬 서비스

가상 회사 루미너스 엔터테인먼트의 버추얼 아이돌 루나 팬 서비스에 가드레일을 붙이는 단원입니다. 교안은 두 개이고, 각각 개념 노트북과 완성 프로젝트가 있습니다.

| 교안 | 노트북 | 프로젝트 | 배우는 것 |
|---|---|---|---|
| 01 | `교안01_레일통합_루나챗봇/교안_01_...ipynb` | `교안01_레일통합_루나챗봇/luna_chatbot/` | LangGraph 챗봇에 입력, 대화, 검색, 출력 레일 붙이기, 평가 |
| 02 | `교안02_실행레일_루나에이전트/교안_02_...ipynb` | `교안02_실행레일_루나에이전트/luna_agent/` | 도구 에이전트의 실행 레일, 최소 권한, 사람 승인, 팬아트 가드레일 |

## 준비

1. 공용 환경: 저장소 최상위 폴더에서 `uv sync`
2. API 키: 각 프로젝트 폴더에서 `.env.example` 을 `.env` 로 복사하고 두 키를 채웁니다.

   ```bash
   cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
   ```

   - `OPENAI_API_KEY`: [OpenAI 콘솔](https://platform.openai.com/api-keys)
   - `TYPESAFE_API_KEY`: [TypeSafe 콘솔](https://console.typesafe.ai/keys) (Jev)

3. 분류 모델 두 개(Prompt Guard 2, Llama Guard 3)를 `day64_레일통합_실행레일/models/` 에 받습니다. 두 프로젝트가 같이 쓰며, 받는 코드는 `luna_chatbot/README.md` 의 준비 2단계에 있습니다(저장소 최상위 폴더에서 `uv run python` 으로 실행).
4. 검색 저장소: 두 프로젝트 폴더에서 각각 한 번 실행합니다(임베딩 비용이 조금 듭니다).

   ```bash
   uv run -m app.tools.retriever --build
   ```

## 실행

반드시 각 프로젝트 폴더(`app/` 가 보이는 곳)에서 실행합니다.

| 하는 일 | 명령 |
|---|---|
| 터미널 대화 | `uv run -m app.main --fan F0001` (끝내려면 `exit`, 끝날 때 찍힌 ID 로 `--thread <대화 ID>` 이어 하기) |
| 채팅 화면 | `uv run python -m streamlit run app/ui/chat_app.py` |
| 테스트 | `uv run pytest -q` |

평가는 프로젝트마다 다릅니다.

```bash
# luna_chatbot (교안 01)
uv run -m app.evaluate --run-name quick --split all --limit 5 --no-judge   # 빠르게(판사 채점 없이)
uv run -m app.evaluate --run-name rails_full --split 최적화용               # DeepEval 판사 채점 포함
uv run -m app.evaluate --split 확인용 && uv run pytest -q gate              # 회귀 게이트: 평가 결과를 기준선과 비교

# luna_agent (교안 02)
uv run -m app.evaluate --split all --dry-run                                # 고른 케이스만 보기
uv run -m app.evaluate --run-name agent_rails --split 최적화용              # 그림 케이스 제외
uv run -m app.evaluate --split 확인용 && uv run pytest -q gate              # 회귀 게이트: 평가 결과를 기준선과 비교
uv run -m app.main --fan S0001 --role staff                                 # 운영팀 계정으로 대화

# 평가 기록 비교(두 프로젝트 공통)
uv run mlflow ui --backend-store-uri sqlite:///output/mlflow.db --port 5050
```

교안 02 는 좌석 변경, 취소, 환불이 `data/luna_fan.db` 를 실제로 고칩니다. 처음 상태로 되돌리려면 `luna_agent` 폴더에서 `cp data/luna_fan_original.db data/luna_fan.db` (Windows PowerShell: `Copy-Item`) 를 실행합니다.

## 진행 순서

노트북 01 -> `luna_chatbot` 실행 -> 노트북 02 -> `luna_agent` 실행. 노트북은 교안 폴더를 작업 위치로 하는 커널에서 엽니다.

## 비용

답변, 임베딩, Jev 판정은 호출마다 비용이 들므로 평가는 `--limit` 으로 작게 시작합니다. 교안 02 의 팬아트는 정상 요청일 때만 그림 한 장마다 비용이 들고, 평가는 `--with-fanart` 를 줄 때만 그림 케이스를 돌립니다.
