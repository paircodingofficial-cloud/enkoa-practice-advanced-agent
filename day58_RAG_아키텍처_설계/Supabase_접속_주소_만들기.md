# Supabase 접속 주소(`SUPABASE_DB_URL`) 만들기

교안 02 4절은 Supabase의 PostgreSQL에 `psycopg2`로 접속합니다. 접속 주소는 아래 순서로 만듭니다.

**왜 URL·KEY가 아니라 이 주소인가**: SQL 단원에서는 `SUPABASE_URL`과 `SUPABASE_ANON_KEY`로 supabase-py를 썼습니다. supabase-py는 REST API로 테이블의 행을 읽고 쓰는 도구라 `CREATE EXTENSION`, `CREATE INDEX` 같은 SQL이나 `pg_relation_size` 같은 크기 측정 함수를 실행할 수 없습니다. 교안 02 4절은 이런 SQL로 pgvector 테이블과 HNSW 인덱스를 만들고 크기를 측정하므로, PostgreSQL에 직접 접속하는 이 주소를 `psycopg2`로 씁니다.

1. [supabase.com](https://supabase.com)에 로그인해 SQL 단원에서 만든 프로젝트를 엽니다. 새로 만든다면 **New project**에서 이름과 **Database Password**를 정하고(따로 적어 둡니다), 리전은 **Northeast Asia (Seoul)** 을 고릅니다.
2. 프로젝트 화면 위쪽의 **Connect** 버튼을 누릅니다.
3. 연결 방식에서 **Session pooler**를 고릅니다. Direct connection 주소는 IPv6 전용이라 IPv4만 쓰는 학교·가정 네트워크에서는 접속이 안 될 수 있습니다.
4. 표시된 주소를 그대로 복사합니다. 모양은 다음과 같고, 호스트(`aws-숫자-리전.pooler.supabase.com`)는 프로젝트마다 다르니 직접 만들지 말고 복사합니다.
   ```
   postgresql://postgres.[PROJECT-REF]:[YOUR-PASSWORD]@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres
   ```
5. `[YOUR-PASSWORD]`를 대괄호까지 지우고 DB 비밀번호로 바꿉니다. 비밀번호에 `@`, `#`, `?`, `&`, `/`, `:`, 공백이 있으면 주소가 깨지므로 퍼센트 인코딩(예: `@` -> `%40`)하거나 영문·숫자만으로 비밀번호를 새로 만듭니다.
6. 이 폴더(또는 저장소 최상위)의 `.env`에 한 줄로 저장합니다. 따옴표는 붙이지 않습니다.
   ```
   SUPABASE_DB_URL=postgresql://postgres.abcdefghijklmnop:내비밀번호@aws-0-ap-northeast-2.pooler.supabase.com:5432/postgres
   ```
7. 교안 02 4절의 접속 셀이 오류 없이 실행되면 접속에 성공한 것입니다.

## DB 비밀번호를 잊었다면

대시보드의 **Database > Settings**에서 **Reset database password**로 새로 만듭니다. 기존 연결은 끊기고, 반영까지 몇 분 걸릴 수 있습니다.

## 자주 나는 오류

| 오류 메시지 | 원인과 해결 |
|---|---|
| `password authentication failed` | 비밀번호가 틀렸거나 특수문자를 인코딩하지 않았습니다. 5번을 다시 확인합니다. |
| `Tenant or user not found` | 사용자 이름이 `postgres.[PROJECT-REF]` 꼴이 아닙니다. Session pooler 주소를 다시 복사합니다. |
| `could not translate host name`, 접속 시간 초과 | Direct connection 주소를 썼거나 프로젝트가 일시정지 상태입니다. Session pooler 주소로 바꾸고, 대시보드에서 프로젝트를 복구합니다. |

`.env`는 비밀번호가 들어 있으니 저장소에 올리거나 다른 사람에게 보내지 않습니다.
