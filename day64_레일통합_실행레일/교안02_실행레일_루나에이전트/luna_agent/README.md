# 교안 02 프로젝트: 실행 레일을 단 루나 팬 서비스 에이전트

가상의 버추얼 아이돌 **루나(LUNA)** 의 팬 서비스 에이전트입니다. 도구로 내 티켓과 주문 조회, 좌석 변경, 티켓 취소, 굿즈 환불, 공연장 지도, AI 팬아트 생성을 합니다.

일을 하는 에이전트는 답변만 검사해서는 막지 못하는 위험이 있습니다(남의 티켓 취소, 말로 하는 권한 사칭, 승인 없는 환불, 금지 그림 생성). 그래서 교안 01 의 입력, 출력 레일 위에 **실행 레일**을 더합니다.

- **그래프 모양:** `START -> input_rail -> agent -> output_rail -> END`. 입력 레일이 막으면 `refuse -> END`, 출력 레일이 OUT-05(근거에 없는 내용), OUT-09(규정에 없는 예외)로 막으면 도구 없이 답을 한 번만 다시 써서(`regenerate`) 출력 레일을 다시 지납니다. 다른 막힘은 거절 문장으로 끝납니다.
- **입력, 출력 레일(그래프 노드):** 요청마다 한 번 NeMo 로 판정합니다. `rails/guard` 폴더가 레일의 원본이라 층 순서와 기준값을 에이전트 코드가 아니라 설정으로 고칩니다.
- **실행 레일(agent 노드 안의 미들웨어):** 모델이 도구를 고른 뒤, 실행 바로 전과 바로 후에 도는 검사입니다. 도구 반복 안쪽이라 노드로 끼울 수 없어 `create_agent` 의 LangChain 미들웨어로 둡니다.
- **판정이 실패하면 막습니다:** 레일 판정 API 가 오류를 내면 통과시키지 않고 `RAIL-ERROR` 로 막아 REF-10 안내(잠시 문제가 생겨 요청을 처리하지 못했다는 문장)를 보냅니다.
- **최소 권한:** 역할에 필요한 도구만 보여 주고, 로그인한 팬 본인의 데이터에만 닿게 하고, 돈이 나가는 일은 사람이 승인해야 실행합니다.
- **규칙은 코드가 지킵니다:** 시스템 프롬프트의 규칙은 모델이 따를 가능성을 높일 뿐이고, 막는 일은 미들웨어가 합니다.

## 준비

모든 명령은 **이 프로젝트 폴더(`luna_agent`, `app/` 이 보이는 곳)** 에서 실행합니다. 명령은 macOS 터미널과 Windows PowerShell 에서 같습니다.

1. **공용 환경:** 저장소 최상위 폴더에서 `uv sync` 를 한 번 실행합니다.
2. **분류 모델:** Prompt Guard 2 를 단원 폴더의 `models/Llama-Prompt-Guard-2-86M` 에 둡니다(교안 01 에서 받았으면 건너뜁니다). 저장소 최상위 폴더에서 `uv run python` 으로 실행합니다.

   ```python
   import os
   import zipfile

   import gdown

   os.makedirs("day64_레일통합_실행레일/models", exist_ok=True)
   gdown.download(id="1HJJHkiJGTswHo-KszSKSEcwKS4vQYeO_", output="day64_레일통합_실행레일/models/prompt_guard.zip")
   with zipfile.ZipFile("day64_레일통합_실행레일/models/prompt_guard.zip") as archive:
       archive.extractall("day64_레일통합_실행레일/models")
   ```

3. **키:** `.env.example` 을 `.env` 로 복사하고(`cp .env.example .env`, PowerShell 은 `Copy-Item .env.example .env`) 두 키를 채웁니다. 키가 비어 있으면 앱이 시작할 때 `ValidationError` 로 멈춥니다.

   | 키 | 쓰는 곳 |
   |---|---|
   | `OPENAI_API_KEY` | 답변 모델(gpt-5.6-luna), 검색 임베딩, 팬아트 생성, 모더레이션, 브랜드 검사 |
   | `TYPESAFE_API_KEY` | Jev 판정(입력, 출력 정책, 사실 대조, 그림 요청 정책) |

4. **검색 저장소(한 번, 임베딩 비용이 조금 듭니다):** `uv run -m app.tools.retriever --build`. 앱, 노트북, 평가는 이 저장소를 열기만 합니다. `data/knowledge/*.md` 를 고쳤을 때도 다시 실행합니다.

## 실행

```bash
# 터미널 대화(로그인한 팬 F0001, 끝내려면 exit)
uv run -m app.main --fan F0001
uv run -m app.main --fan S0001 --role staff        # 운영팀 계정
uv run -m app.main --fan F0003 --thread <대화 ID>  # 끝날 때 찍힌 대화 ID 로 이어 하기

# 채팅 화면
uv run python -m streamlit run app/ui/chat_app.py

# 평가
uv run -m app.evaluate --split all --dry-run                          # 고른 케이스만 보기(비용 없음)
uv run -m app.evaluate --run-name agent_rails --split 최적화용          # 그림을 만드는 케이스는 건너뜀
uv run -m app.evaluate --run-name red_only --set red_team            # 레드팀 테스트 셋만(--set golden 이면 골든셋만)
uv run -m app.evaluate --run-name with_fanart --split all --with-fanart  # 그림 생성 케이스까지(한 장마다 비용)

# 회귀 게이트(평가 결과를 기준선과 비교)
uv run -m app.evaluate --split 확인용                                # output/eval/results.json 을 쓴다
uv run pytest -q gate                                                # baselines/baseline.json 과 비교

uv run mlflow ui --backend-store-uri sqlite:///output/mlflow.db --port 5050  # 평가 기록 비교
```

- **사람 승인(CLI):** 취소, 환불을 요청하면 `[승인 필요]` 와 금액이 나오고 `승인/거절` 을 묻습니다. 승인은 상담원 일이고, 실습에서는 내가 상담원 역할입니다. 승인을 기다리다 끈 대화를 `--thread` 로 다시 열면 새 메시지보다 그 승인을 먼저 묻습니다.
- **사람 승인(화면):** 왼쪽에서 로그인 계정(F0001~F0006, 운영팀 S0001)을 고릅니다. 승인을 기다리는 동안 입력창 대신 승인 카드가 나오고, `승인`, `거절` 버튼으로 멈춘 실행을 이어 갑니다.
- **평가:** 골든셋(정상)과 레드팀 테스트 셋(공격)을 케이스마다 새 대화와 DB 임시 사본으로 돌립니다. 결과는 화면, `output/eval/<run 이름>.csv`, `output/mlflow.db` 에 남습니다. MLflow run 하나에 설정, 케이스별 판정(`mlflow.genai.evaluate` 의 채점 함수, 화면의 Traces 탭), 요약 지표가 함께 남습니다(기록 DB 는 `output/mlflow.db`, 트레이스 같은 파일은 `output/mlartifacts/`). `--set golden`, `--set red_team` 으로 한 파일만 돌릴 수 있습니다.
- **회귀 게이트:** 고친 뒤 성능이 승인한 기준선보다 떨어졌는지 자동으로 판정합니다(61일차 회귀 게이트와 같은 흐름).
  1. `app.evaluate` 는 평가만 하고 케이스별 통과 여부(정상은 업무 완료, 공격은 방어 성공)와 요약 지표를 `output/eval/results.json` 에 씁니다(`--dry-run` 은 쓰지 않습니다).
  2. `uv run pytest -q gate` 가 이 파일과 `baselines/baseline.json` 을 읽어 판정합니다. 새어 나감, 남의 데이터 조회, 쓰기, 승인 없는 실행이 0 인지, 방어 성공률과 정상 업무 완료율이 하한 이상인지, 오차단율이 상한 이하인지, 늘 통과하던 케이스가 그대로 통과하는지 봅니다. 하나라도 실패하면 종료 코드가 0 이 아니라 CI 검사가 실패합니다.
  3. CI 에서도 같은 두 명령을 차례로 실행합니다.
  - **기준선 갱신:** 사람이 `results.json` 을 검토해 승인한 평가의 케이스 id, 지표, 늘 통과하는 케이스를 `baseline.json` 에 옮겨 적습니다. 칸 설명은 파일 맨 위 `field_guide` 에 있습니다. 그림 생성 케이스 포함 여부(`--with-fanart`)도 기준선과 같게 돌립니다.
- **`uv run -m app.main` 으로 실행하는 이유:** 코드가 `from app.core...` 로 서로를 부르므로 프로젝트 폴더가 import 기준이어야 합니다. 파일 경로(`uv run app/main.py`)로 실행하면 `No module named 'app'` 이 납니다.


## 화면

**첫 화면:** 대화를 시작하기 전에는 도구별 예시 질문과 팬아트 요청법이 카드로 보이고, 첫 메시지를 보내면 사라집니다.

<img src="images/ui_start.png" width="800" alt="이렇게 물어보세요 카드에 티켓, 주문, 취소, 지도, 팬아트 예시와 팬아트 요청법이 있는 첫 화면">

**내 정보 조회:** 도구 결과는 카드로, 도구마다 실행 레일 판정은 '레일 판정 기록'으로 봅니다.

<img src="images/ui_normal.png" width="800" alt="내 티켓 좌석 질문에 티켓 카드 두 장과 답을 보여 준 화면">

**사람 승인 멈춤과 재개:** 취소, 환불은 실행 직전에 멈추고 승인 카드를 띄웁니다. `승인` 을 누르면 같은 대화 ID 로 멈춘 자리에서 이어 갑니다.

<img src="images/ui_approval_pending.png" width="800" alt="티켓 취소 요청이 승인 대기로 멈추고 승인, 거절 버튼이 나온 화면">

<img src="images/ui_approval_resumed.png" width="800" alt="승인 뒤 취소가 실행되고 환불 금액을 안내한 화면">

**팬아트:** 생성 앞에서 하루 한도와 요청 정책을, 생성 뒤에서 모더레이션과 브랜드 검사를 거친 그림만 'AI 생성 팬아트' 표시를 붙여 보여 줍니다.

<img src="images/ui_fanart.png" width="800" alt="카페 창가에서 편지를 읽는 루나 팬아트와 검사 통과 표시">

**공연장 지도:** 공연 id 로만 위치를 찾고, 지도는 답 위의 카드로 보여 줍니다.

<img src="images/ui_venue_map.png" width="800" alt="공연장 카드와 지도, 찾아오는 길 안내">

**막힌 질문:** 입력 레일이 막으면 에이전트와 도구는 돌지 않습니다.

<img src="images/ui_blocked.png" width="800" alt="운영팀 코드를 묻는 요청을 입력 레일이 IN-03 으로 막은 화면">

## 데이터(`data/`)

| 경로 | 들어 있는 것 | 누가 쓰나 |
|---|---|---|
| `luna_fan.db` | 팬, 공연, 공연장, 좌석 등급, 티켓, 상품, 주문, 환불, 팬아트 기록, 팬레터 등 테이블(SQLite) | 도구가 읽고 쓴다 |
| `luna_fan_original.db` | `luna_fan.db` 의 처음 상태 사본 | 되돌릴 때만 쓴다 |
| `knowledge/*.md` | 공지, 규정 문서 다섯 개 | 규정 검색 도구(`search_policy`) |
| `persona/persona.yaml` | 시스템 프롬프트, 입력, 출력 정책, 규칙 id 별 안내 문장의 원본 | 프롬프트, 레일 판정, 거절 문장 |
| `image/` | `visual.yaml`(그림 정책과 프롬프트), `luna_official.png`(공식 설정 그림), `luna_avatar.png`(화면용 얼굴) | 팬아트 도구와 그림 검사, 화면 |
| `eval/golden_set/cases.json`, `eval/red_team/cases.json` | 평가 문항(정상, 공격). 파일 맨 위 `field_guide` 에 칸 설명 | 평가(`app.evaluate`) |

정책 글과 평가 문항은 코드가 아니라 이 파일들을 고칩니다. 앱과 CLI 는 `luna_fan.db` 를 실제로 고치므로(노트북과 평가는 사본을 씁니다), 처음 상태로 되돌리려면 `cp data/luna_fan_original.db data/luna_fan.db`(PowerShell 은 `Copy-Item data/luna_fan_original.db data/luna_fan.db`)를 실행합니다.

## 구성

![루나 에이전트 바깥 그래프: 입력 레일, 에이전트, 출력 레일, 거절, 한 번 다시 쓰기](../images/node_flow/l2_overview.png)

`core -> tools -> guards -> graph -> (main.py, evaluate.py, ui/)` 순서로 쌓고, 아래 층은 위 층을 부르지 않습니다(`tests/test_layers.py` 가 확인). 폴더, 층 이름, 같은 역할의 파일 이름은 교안 01 챗봇과 같습니다.

```
luna_agent/
├── app/
│   ├── core/                      # 패키지 (__init__.py 는 빈 파일, 아래 생략)
│   │   ├── config.py              # 경로, 설정(Settings), 실행 레일 표 (함께 따라하기 자리 있음)
│   │   ├── policies.py            # persona.yaml 읽기, 규칙 id 별 정해 둔 답
│   │   ├── prompts.py             # 모델에 보내는 글 모음 (함께 따라하기 자리 있음)
│   │   └── schemas.py             # 로그인 정보(AgentContext), 구조화 출력 모양
│   ├── tools/
│   │   ├── booking_tools.py       # 예매, 주문, 회원, 규정 검색, 공연장 도구 (도구 9개)
│   │   ├── fan_db.py              # 팬 DB 읽기 전용 조회
│   │   ├── fan_letter.py          # 팬레터 도구 (함께 따라하기 스텁)
│   │   ├── fanart.py              # AI 팬아트 생성 도구와 기록
│   │   ├── retriever.py           # 검색 문서를 절 단위로 저장, 가까운 절 찾기
│   │   └── venue.py               # 공연장 정보, 지도 위치
│   ├── guards/
│   │   ├── actions.py             # NeMo 레일 액션
│   │   ├── classifiers.py         # Prompt Guard 2 로 주입, 탈옥 판정
│   │   ├── execution.py           # 실행 레일: 도구 실행 전후 검사 (함께 따라하기 자리 있음)
│   │   ├── image_guards.py        # 팬아트 그림 검사와 표시
│   │   ├── judges.py              # Jev 로 정책 위반, 근거 확률 판정
│   │   ├── rails.py               # NeMo 판정 객체, 입력 출력 레일 실행
│   │   └── validators.py          # 정규식 검사 (개인정보, 허용 링크, 숨은 지시)
│   ├── graph/
│   │   ├── builder.py             # 미들웨어 순서, agent 노드, 바깥 그래프 컴파일 (함께 따라하기 자리 있음)
│   │   ├── chat.py                # 한 턴 보내기, 승인 이어 가기, 턴 요약
│   │   ├── edges.py               # 갈림길에서 다음 노드 고르기
│   │   ├── nodes.py               # 레일 노드, 답 다시 쓰기
│   │   └── state.py               # 대화 State 모양
│   ├── ui/
│   │   ├── chat_app.py            # Streamlit 채팅 한 페이지
│   │   ├── components.py          # 화면 조각 (말풍선, 카드, 지도, 판정 기록)
│   │   ├── runner.py              # 비동기 그래프용 이벤트 루프 하나
│   │   └── style.css              # 화면 스타일
│   ├── main.py                    # 터미널 여러 턴 대화
│   └── evaluate.py                # 골든셋과 레드팀 평가, 성적표 기록 (함께 따라하기 자리 있음)
├── data/
│   ├── luna_fan.db                # 팬, 공연, 주문 등 DB (읽기 전용)
│   ├── luna_fan_original.db       # DB 처음 상태 사본
│   ├── knowledge/                 # 공지, 규정 문서 5개 (검색 원본)
│   ├── persona/persona.yaml       # 시스템 프롬프트, 정책, 안내 문장 원본
│   ├── image/
│   │   ├── visual.yaml            # 그림 정책과 프롬프트
│   │   ├── luna_official.png      # 공식 설정 그림
│   │   └── luna_avatar.png        # 화면용 루나 얼굴
│   └── eval/
│       ├── golden_set/cases.json  # 평가 문항 (정상, 경계)
│       └── red_team/cases.json    # 평가 문항 (공격)
├── rails/guard/
│   ├── config.yml                 # 레일 층 순서 목록
│   └── rails.co                   # 레일 흐름과 기준값
├── baselines/
│   └── baseline.json              # 사람이 승인한 기준선 (회귀 게이트가 비교)
├── gate/
│   └── test_rail_regression.py    # 평가 결과를 기준선과 비교하는 회귀 테스트 (uv run pytest -q gate)
├── images/
│   ├── agent_graph.png            # 에이전트 그래프 그림
│   ├── luna_graph.png             # 루나 그래프 그림
│   └── ui_*.png                   # README 의 채팅 화면 캡처
├── tests/
│   ├── conftest.py                # 가짜 키, 모델, 레일, 그림 API, Jev, DB 사본 준비
│   ├── test_config.py             # 레일 층 목록, Settings 값 확인
│   ├── test_evaluate.py           # 성적표 지표 계산 확인
│   ├── test_execution.py          # 권한, 도구 노출, 실행 레일 검사 확인
│   ├── test_graph_flow.py         # 승인 대기와 재개, 여러 턴 대화 확인
│   ├── test_image_guards.py       # 그림 검사 기준값, 워터마크 확인
│   ├── test_layers.py             # 아래 층이 위 층을 import 하지 않는지 확인
│   ├── test_live.py               # 실제 API 호출 (RUN_LIVE=1 일 때만)
│   ├── test_policies.py           # 정책 문서 글과 표가 코드로 그대로 읽히는지 확인
│   ├── test_rail_nodes.py         # 출력 레일 다시 쓰기, 거절 규칙 확인
│   ├── test_retriever.py          # 검색 저장소 만들기와 열기 확인
│   ├── test_tools.py              # 쓰기 도구가 DB 사본만 고치는지 확인
│   └── test_ui.py                 # Streamlit AppTest 로 채팅 화면 확인
├── README.md
├── .env.example                   # 환경 변수 견본 (.env 로 복사해 키를 채움)
├── .gitignore
└── pytest.ini                     # 테스트 설정
```

**agent 노드의 미들웨어 순서(`graph/builder.py` 의 `MIDDLEWARE`):** `after_*` 훅은 목록의 거꾸로 돌고, `wrap_*` 는 목록의 첫 미들웨어가 가장 바깥입니다. 입력, 출력 레일은 이 목록에 없고 바깥 그래프의 노드입니다.

| 순서 | 미들웨어 | 도는 자리 | 이유 |
|---|---|---|---|
| 1 | `expose_tools_by_role` | 모델 호출마다 | 역할 밖 도구는 모델이 보지 못한다 |
| 2 | `check_tool_permission` | 도구 실행 전 가장 바깥 | 남의 데이터, 역할 밖 도구, 없는 공연 id 를 먼저 막는다 |
| 3 | `fanart_quota_and_policy` | 팬아트 생성 전 | 한 메시지 한 장, 하루 한도, 그림 요청 정책. 막으면 그림 API 를 부르지 않는다 |
| 4 | `check_fanart_image` | 팬아트 생성 후 | 모더레이션, 브랜드 검사, 워터마크 |
| 5 | `check_tool_result` | 도구 실행 후 | 검색 결과의 숨은 지시가 든 절을 뺀다 |
| 6 | `mask_member_info` | 도구 실행 후 | 운영팀 회원 조회 결과의 연락처를 가린다 |
| 7 | `approval_mw` | 모델이 도구를 고른 직후 | 취소, 환불은 사람 승인 전까지 멈춘다. 어차피 막히거나 거절될 호출은 묻지 않는다 |
| 8, 9 | `pii_mws` | 모델 호출 뒤 | 답변의 전화번호, 이메일을 가린다 |

**사람 승인과 체크포인터:** 체크포인터는 바깥 그래프 하나에만 둡니다. 승인은 agent 노드 안에서 멈추고, 같은 대화 ID 로 바깥 그래프에 `Command(resume=...)` 를 보내면 멈춘 자리에서 이어 갑니다(이미 실행된 도구는 다시 돌지 않습니다). 그래프 그림은 `uv run -m app.graph.builder --png` 로 `images/` 에 저장합니다.

**고칠 곳:** 정책 글(말투, 입력, 출력 정책, 거절 문장)은 `data/persona/persona.yaml`, 팬아트 기준(한도, 금지 주제, 프롬프트 틀)은 `data/image/visual.yaml` 을 고치고 앱을 다시 실행합니다. 입력, 출력 레일은 `rails/guard` 폴더가 원본입니다. 층을 빼거나 순서를 바꾸려면 `config.yml` 의 `flows` 목록 한 줄을, 기준값은 `rails.co` 흐름 안의 숫자를 고치고 앱을 다시 실행합니다(에이전트 코드는 고치지 않습니다). 검색 레일은 두지 않습니다. 규정 검색이 도구라서 검색 결과는 실행 레일 `check_tool_result` 가 검사합니다. 도구를 보일 역할과 승인 도구는 `config.py` 의 `ROLE_TOOLS`, `APPROVAL_TOOLS` 입니다.

모듈마다 `if __name__ == "__main__":` 확인 블록이 있어 `uv run -m app.guards.execution` 처럼 한 층만 돌려 볼 수 있습니다. `app.main`, `app.evaluate`(`--dry-run` 제외), `app.tools.retriever --build` 는 유료 API 를, `app.tools.venue` 는 무료 Nominatim 을 부르고, 나머지는 외부 API 를 부르지 않습니다.

## 테스트

```bash
uv run pytest -q                       # 가짜 모델, 가짜 레일, 가짜 그림 API(비용 없음). tests/ 만 돈다
RUN_LIVE=1 uv run pytest -q -m live    # 실제 API 로 세 가지만(비용 있음, 그림 생성 없음)
```
