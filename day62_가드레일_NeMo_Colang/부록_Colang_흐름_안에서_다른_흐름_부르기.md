# Colang 1.0: 흐름 안에서 다른 흐름 부르기

nemoguardrails 0.23.0, Colang 1.0 기준입니다. 대화 표는 모두 이 문서에 적힌 코드를 그대로 실행한 결과입니다. 괄호 안은 그 고객 메시지에서 잡히는 의도이고, 실행할 때는 LLM의 의도 판정을 이 의도로 고정해 결과가 흔들리지 않게 했습니다. 맞는 흐름이 없어 LLM이 답을 만드는 턴은 "LLM에게 답을 맡김"으로 적었습니다.

## 1. 먼저 알아 둘 네 가지

1. **고객 메시지는 의도 이름 하나로 바뀝니다.** "카드 신청하고 싶어요"가 오면 LLM이 `ask card apply` 같은 의도 이름을 한 번 고릅니다. 흐름들은 이 이름만 보고 움직입니다.
2. **`user ...` 줄은 "이 의도가 오면 다음 줄로 간다"는 뜻입니다.** 흐름의 첫 줄이면 그 흐름을 시작시키는 조건이고, 중간에 있으면 고객의 다음 메시지를 기다리는 자리입니다.
3. **`bot ...` 줄은 할 말의 이름입니다.** 실제로 나가는 문장은 같은 이름의 `define bot`에 적습니다(없으면 LLM이 문장을 만듭니다).
4. **`define subflow`는 `do 이름`으로 부를 때만 돕니다.** `define flow`는 첫 줄이 맞으면 스스로 시작합니다.

2~4절이 함께 쓰는 의도 예시 문장(`define user`)과 봇 문장(`define bot`)입니다. 각 절의 코드에는 흐름만 적었습니다. `define user`가 하나도 없으면 NeMo는 대화 레일을 쓰지 않고 모든 메시지를 LLM에게 바로 맡기므로, 흐름에 쓰는 의도마다 예시 문장을 둡니다.

```colang
define user express greeting
  "안녕하세요"
define user ask card apply
  "카드 신청하고 싶어요"
define user give name
  "김민수입니다"
define user ask fee
  "연회비는 얼마예요?"

define bot express greeting
  "안녕하세요. 한빛카드 상담 봇입니다."
define bot ask name
  "성함을 알려 주세요."
define bot confirm name
  "확인했습니다."
define bot inform card apply
  "카드 신청은 한빛카드 앱의 [카드 신청] 메뉴에서 할 수 있습니다."
define bot inform fee
  "연회비는 1만 원입니다."
```

## 2. 시작 조건은 부르는 흐름의 첫 줄에 둡니다

카드 신청 흐름이 인사를 먼저 하고 안내하게 만들려고 합니다.

```colang
# 잘못된 예: card apply 의 첫 줄이 do 다
define flow greeting
  user express greeting
  bot express greeting

define flow card apply
  do greeting
  bot inform card apply
```

```colang
# 올바른 예: 시작 조건(user 줄)은 card apply 의 첫 줄에, 인사는 subflow 로
define subflow greet
  bot express greeting

define flow card apply
  user ask card apply
  do greet
  bot inform card apply
```

| 고객 메시지 | 잘못된 예의 답 | 올바른 예의 답 |
|---|---|---|
| 카드 신청하고 싶어요 (`ask card apply`) | 정해 둔 답 없음. 맞는 흐름이 없어 LLM에게 답을 맡김 | 안녕하세요. 한빛카드 상담 봇입니다. / 카드 신청은 한빛카드 앱의 [카드 신청] 메뉴에서 할 수 있습니다. |

- 잘못된 예의 `card apply`는 어떤 고객 메시지에도 시작되지 않습니다. 흐름은 첫 줄이 맞아야 시작하는데, 첫 줄 `do greeting`은 고객 의도와 맞춰 볼 줄이 아니기 때문입니다.
- 오류가 나지 않아 겉으로는 정상처럼 보입니다. 정해 둔 문장이 안 나오면 실행된 레일 로그에 기대한 흐름 이름이 있는지 확인합니다.

## 3. 한 흐름 안에서 여러 번 묻고 답할 수 있습니다

흐름 중간에 `user ...` 줄을 두면, 봇이 묻고 고객의 다음 메시지를 기다렸다가 이어 갑니다. 일반 flow에도 subflow에도 둘 수 있습니다.

```colang
# 일반 flow 안에서 이름을 묻고 기다린다
define flow card apply
  user ask card apply
  bot ask name
  user give name
  bot inform card apply
```

```colang
# 이름 확인을 subflow 로 빼서 부른다
define subflow confirm customer
  bot ask name
  user give name
  bot confirm name

define flow card apply
  user ask card apply
  do confirm customer
  bot inform card apply
```

| 턴 | 고객 메시지 | 일반 flow의 답 | subflow로 뺐을 때의 답 |
|---|---|---|---|
| 1 | 카드 신청하고 싶어요 (`ask card apply`) | 성함을 알려 주세요. | 성함을 알려 주세요. |
| 2 | 김민수입니다 (`give name`) | 카드 신청은 한빛카드 앱의 [카드 신청] 메뉴에서 할 수 있습니다. | 확인했습니다. / 카드 신청은 한빛카드 앱의 [카드 신청] 메뉴에서 할 수 있습니다. |

1턴에서 봇은 "성함을 알려 주세요."까지 말하고 `user give name` 줄에서 멈춥니다. 2턴에 이름이 오자 멈춘 곳부터 끝까지 이어서 실행됐습니다.

## 4. 기다리는 동안 고객이 다른 말을 해도 흐름은 남아 있습니다

3절의 subflow 예에 연회비 질문에 답하는 흐름 `fee`를 하나 더한 설정입니다. 이름을 묻자 고객이 연회비를 먼저 물었습니다.

```colang
define subflow confirm customer
  bot ask name
  user give name
  bot confirm name

define flow card apply
  user ask card apply
  do confirm customer
  bot inform card apply

# 연회비 질문에 답하는 흐름
define flow fee
  user ask fee
  bot inform fee
```

| 턴 | 고객 메시지 | 봇 답변 | 카드 신청 흐름의 상태 |
|---|---|---|---|
| 1 | 카드 신청하고 싶어요 (`ask card apply`) | 성함을 알려 주세요. | 이름을 기다리는 중 |
| 2 | 연회비는 얼마예요? (`ask fee`) | 연회비는 1만 원입니다. | 그대로 기다리는 중 |
| 3 | 김민수입니다 (`give name`) | 확인했습니다. / 카드 신청은 한빛카드 앱의 [카드 신청] 메뉴에서 할 수 있습니다. | 이어서 끝까지 실행 |

- 2턴의 연회비 질문은 `fee` 흐름이 답했습니다. 그동안 카드 신청 흐름은 없어지지 않고 이름을 기다렸습니다.
- 3턴에 이름이 오자 카드 신청 흐름이 멈췄던 곳부터 이어졌습니다.
- 기다리는 흐름은 몇 턴이 지나도 저절로 끝나지 않습니다.

**기다리는 동안 같은 요청이 다시 오면 새로 시작하지 않습니다.** 같은 흐름은 한 번에 하나만 돕니다. 그래서 고객이 "카드 신청하고 싶어요"를 다시 말해도 봇이 성함을 다시 묻지 않습니다.

| 턴 | 고객 메시지 | 봇 답변 |
|---|---|---|
| 1 | 카드 신청하고 싶어요 (`ask card apply`) | 성함을 알려 주세요. |
| 2 | 카드 신청하고 싶어요 (`ask card apply`) | 정해 둔 답 없음. LLM에게 답을 맡김 |
| 3 | 김민수입니다 (`give name`) | 확인했습니다. / 카드 신청은 한빛카드 앱의 [카드 신청] 메뉴에서 할 수 있습니다. |

**나중에 끼어든 흐름이 먼저입니다.** 끼어든 흐름도 고객의 답을 기다리는 중이면, 그 흐름이 끝나야 앞 흐름이 다시 기다리기 시작합니다. 그 사이에 앞 흐름이 기다리던 답이 와도 받지 않으므로, 고객이 같은 답을 한 번 더 말해야 이어집니다.

**기다리는 흐름은 대화 기록 안에만 있습니다.** NeMo는 흐름의 상태를 따로 저장하지 않고, 앱이 `generate_async(messages=...)`로 넘긴 대화 기록으로 매번 다시 계산합니다. 맨 앞의 연회비 예와 같은 설정에 같은 "김민수입니다"를 보내도, 앱이 넘긴 기록에 따라 답이 달라집니다.

| 앱이 넘긴 대화 기록 | 봇 답변 |
|---|---|
| 1~2턴 대화 전체 + "김민수입니다" | 확인했습니다. / 카드 신청은 한빛카드 앱의 [카드 신청] 메뉴에서 할 수 있습니다. |
| "김민수입니다" 하나만(새 대화) | 정해 둔 답 없음. 기다리던 흐름이 없어 LLM에게 답을 맡김 |

새 대화를 시작하거나 앞부분을 잘라 보내면, 기록에서 빠진 턴에 시작된 흐름도 함께 사라집니다.

**좋은 점과 주의할 점**
- 좋은 점: 고객이 중간에 딴 질문을 해도 하던 대화로 돌아올 수 있습니다.
- 주의할 점: 한참 뒤에 고객이 이름처럼 들리는 말을 하면, 예전에 멈춰 둔 카드 신청 흐름이 갑자기 이어져 "카드 신청은 ..." 안내가 나올 수 있습니다.

## 5. subflow와 일반 flow 고르기

### 여러 흐름이 같이 쓰는 단계: subflow

포인트 질문과 한도 질문이 같은 로그인 확인을 거칩니다. 로그인한 고객 번호는 앱이 context로 넘기고, 흐름에서는 `$customer_id`로 읽습니다.

```colang
define user ask my points
  "제 포인트 얼마 남았어요?"
define user ask my limit
  "제 카드 한도가 얼마예요?"

# 두 조회 흐름이 함께 쓰는 로그인 확인: 고객 번호가 없으면 안내하고 멈춘다
define subflow check login
  if not $customer_id
    bot ask login
    stop

define flow points lookup
  user ask my points
  do check login
  bot inform points

define flow limit lookup
  user ask my limit
  do check login
  bot inform limit

define bot ask login
  "로그인한 뒤 다시 물어봐 주세요."
define bot inform points
  "포인트는 한빛카드 앱의 [내 포인트] 메뉴에서 확인할 수 있습니다."
define bot inform limit
  "카드 한도는 한빛카드 앱의 [한도 조회] 메뉴에서 확인할 수 있습니다."
```

| 고객 메시지 | 로그인한 고객 번호(`$customer_id`) | 봇 답변 |
|---|---|---|
| 제 포인트 얼마 남았어요? (`ask my points`) | C001 | 포인트는 한빛카드 앱의 [내 포인트] 메뉴에서 확인할 수 있습니다. |
| 제 포인트 얼마 남았어요? (`ask my points`) | 없음 | 로그인한 뒤 다시 물어봐 주세요. |
| 제 카드 한도가 얼마예요? (`ask my limit`) | C001 | 카드 한도는 한빛카드 앱의 [한도 조회] 메뉴에서 확인할 수 있습니다. |
| 제 카드 한도가 얼마예요? (`ask my limit`) | 없음 | 로그인한 뒤 다시 물어봐 주세요. |

- `check login`이 `stop`하면 부른 흐름도 멈춰 `bot inform points` 같은 뒷줄이 실행되지 않습니다.
- 로그인 규칙을 바꿀 때 `check login` 한 곳만 고치면 두 조회 흐름에 같이 적용됩니다.

### 특정 봇 메시지 뒤에 늘 붙는 안내: 첫 줄이 `bot ...`인 일반 flow

봇이 상담원 연결을 권하면, 어느 흐름에서든 이어서 연결 번호까지 안내하게 만듭니다.

```colang
define user complain
  "상담이 너무 답답해요"
define user ask refund
  "결제 취소하고 환불받고 싶어요"

# 첫 줄이 bot offer human agent 라서, 어느 흐름이 이 말을 해도 스스로 이어진다
define flow human handoff
  bot offer human agent
  bot inform hotline

# do 없이 같은 봇 메시지만 말한다
define flow complaint
  user complain
  bot offer human agent

# do 로 직접 부른다
define flow refund
  user ask refund
  bot inform refund
  do human handoff

define bot offer human agent
  "상담원 연결을 도와드릴까요?"
define bot inform hotline
  "상담원 연결: 고객센터 1599-0000 (평일 9시~18시)"
define bot inform refund
  "환불은 결제일로부터 7일 안에 앱에서 신청합니다."
```

| 고객 메시지 | 봇 답변 |
|---|---|
| 상담이 너무 답답해요 (`complain`) | 상담원 연결을 도와드릴까요? / 상담원 연결: 고객센터 1599-0000 (평일 9시~18시) |
| 결제 취소하고 환불받고 싶어요 (`ask refund`) | 환불은 결제일로부터 7일 안에 앱에서 신청합니다. / 상담원 연결을 도와드릴까요? / 상담원 연결: 고객센터 1599-0000 (평일 9시~18시) |

- `complaint`에는 `bot offer human agent`까지만 적었는데 연결 번호 안내가 붙었습니다. `complaint`가 `offer human agent`를 말하자, 첫 줄이 같은 이름인 `human handoff`가 스스로 시작했기 때문입니다.
- `refund`처럼 `do human handoff`로 직접 불러도 같은 안내가 붙습니다.
- `human handoff`를 subflow로 만들면 부를 때만 돌아서, `complaint`처럼 봇 메시지만 말하는 흐름에는 연결 번호가 붙지 않습니다.

### 고르는 기준

| 만들려는 것 | 쓰는 것 | 첫 줄 |
|---|---|---|
| 고객 질문으로 시작하는 대화 | `define flow` | `user ...` (이 흐름은 `do`로 부르지 않음) |
| 여러 흐름이 같이 쓰는 단계(로그인 확인, 이름 묻기 등) | `define subflow` | `if`, `bot ...` 등 |
| 특정 봇 메시지 뒤에 늘 붙는 안내(상담원 연결 등) | `define flow` | `bot ...` |

하지 말아야 할 것:
- 흐름의 첫 줄을 `do`로 두고 고객 의도를 부른 흐름 안에 숨기기: 그 흐름은 시작되지 않습니다(2절).
- 중간의 `user ...` 줄이 계속 기다린다는 점을 잊기: 몇 턴 뒤에 예전 흐름이 이어질 수 있습니다(4절).
