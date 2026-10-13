# GuardFall2

Django 기반 낙상 의심 감지·영상 분석·모델 학습 플랫폼입니다. 어깨와 무릎의 자세 좌표를 수집하고 규칙 또는 학습 모델로 판정합니다. 연속 낙상 의심 프레임을 이벤트로 기록하고 사용자가 실제 낙상 또는 오탐 여부를 확인할 수 있습니다.

## 주요 기능

| 기능 | 업무 내용 |
|---|---|
| 대시보드 | 내 감지 세션, 미확인 이벤트, 사용 가능한 모델, 대기 작업 집계 |
| 영상 분석 | 영상 업로드, 프레임별 관절 좌표 추출, 규칙 라벨 생성, CSV 다운로드 |
| 모델 학습 | CSV를 이용한 Dense·LSTM·결합 앙상블 학습, 검증 지표 저장 |
| 모델 적용 | ZIP 모델 재로딩 검증, 활성화, 사용자별 사용 권한 지정 |
| 실시간 감지 | 브라우저 카메라 프레임 전송, 서버 자세 추출, 낙상 의심 이벤트 생성 |
| 감지 기록 | 상태 조회, 확인·오탐 처리, 메모 입력, XLSX 다운로드 |
| 감지 설정 | 관절 신뢰도, Y 좌표 기준, 확률 임계값, 연속 프레임, 재알림 간격 |
| 알림 연결 | 사용자별 Telegram 연결 정보 암호화 저장, 전송 대기열과 재시도 |
| 시스템 관리 | Django Admin에서 사용자·그룹·3단 메뉴·감사 로그 관리 |

## 기술 구성

- Python 3.12, Django 5.2 LTS, uv와 고정된 `uv.lock`
- Django Templates, 로컬 CSS·JavaScript, 반응형 3단 메뉴, 다크 모드
- 기본 SQLite; 선택적으로 PostgreSQL 또는 MariaDB
- MediaPipe 0.10.21 및 OpenCV: 영상·이미지의 자세 좌표 추출
- TensorFlow/Keras: 16개 특징을 사용하는 낙상 분류 모델
- Fernet: 알림 연결 토큰과 Chat ID 암호화
- openpyxl: XLSX 내보내기, 수식으로 해석될 수 있는 문자열 이스케이프
- 운영 구성: Gunicorn + Nginx + systemd 웹 서비스와 작업 처리 서비스

영상·학습 의존성은 선택 설치입니다. 기본 웹 서버, 인증, 설정, 기록과 좌표 입력 API는 대용량 ML 패키지 없이 실행됩니다.

## 시작하기

```bash
git clone https://github.com/mycodehive/guardFall2.git
cd guardFall2
cp .env.example .env
uv sync --frozen
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

`http://127.0.0.1:8000/`에서 로그인합니다. 기본 계정이나 고정 비밀번호는 생성하지 않습니다. `migrate` 실행으로 기본 메뉴가 자동 등록됩니다.

전체 감지·학습 기능을 사용하려면:

```bash
uv sync --frozen --extra vision --extra ml
uv run --extra vision --extra ml python manage.py runserver
```

**uv 실행 시 필요한 extras를 유지하세요.** 기본 `uv run`은 선택 패키지를 제거할 수 있으므로 영상·학습 실행에는 `--extra vision --extra ml`을 함께 지정합니다.

`.env`의 `DJANGO_SECRET_KEY`를 충분히 긴 임의 문자열로 변경합니다. 알림을 사용한다면 다음 명령으로 암호화 키를 생성해 `GUARDFALL_ENCRYPTION_KEY`에 설정합니다.

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 역할 및 권한

- 일반 사용자: 자신의 실시간 감지·기록·알림 설정, 지정받은 활성 모델 사용
- `is_staff` 사용자: 위 기능과 자신의 영상 분석·모델 학습·모델 적용, 공통 감지 설정
- 최고관리자: Django Admin에서 사용자·그룹·메뉴 관리
- 메뉴 그룹 지정은 선택 사항입니다. 지정되면 해당 그룹 소속자만 접근할 수 있으며 상위 메뉴의 권한과 활성 여부도 검사합니다.
- 메뉴를 숨기는 것에 그치지 않고 직접 URL 접근에서도 권한을 검사합니다.
- 업무 데이터는 작성자 기준으로 격리합니다. 최고관리자라도 다른 사용자의 영상·세션·이벤트를 업무 화면에서 자동 조회하지 않습니다.
- 모델 작성자는 일반 사용자에게 모델 사용 권한을 부여할 수 있습니다. 이 권한은 모델 실행에 한정되며 학습 입력 파일이나 모델 파일 다운로드 권한을 부여하지 않습니다.
- Admin의 사용자·그룹 관리 권한은 Django의 모델 권한을 따릅니다. 공통 감지 기준은 staff 전용 업무 화면에서 관리합니다.

## 비즈니스 로직

### 1. 관절 좌표와 규칙 판정

사용하는 관절은 왼쪽 어깨, 오른쪽 어깨, 왼쪽 무릎, 오른쪽 무릎입니다. 각 관절에 대해 `x`, `y`, `v`(visibility), `vr`(유효 여부)를 기록하여 총 16개 특징을 구성합니다.

| 항목 | 기본값 |
|---|---:|
| 유효 관절의 visibility 기준 | 0.70 |
| 최소 유효 관절 수 | 3 |
| 왼쪽·오른쪽 어깨 Y 기준 | 각각 0.55 |
| 왼쪽·오른쪽 무릎 Y 기준 | 각각 0.65 |
| Y 기준을 충족해야 하는 관절 수 | 3 |
| 학습 모델의 낙상 확률 기준 | 0.50 |
| 이벤트 생성에 필요한 연속 프레임 수 | 10 |
| 이벤트 간 최소 간격 | 30초 |

유효 관절 수가 부족하면 `-1`(판별 불가)입니다. 충분한 관절이 보이고 Y 기준을 충족하는 관절 수가 설정값 이상이면 `1`(낙상 의심), 아니면 `0`(정상)입니다. 규칙은 화면 내 위치에 의존하므로 카메라 높이·구도에 따라 설정을 조정해야 합니다. 규칙 라벨은 정답을 보증하지 않습니다.

### 2. 영상 분석과 학습 데이터

관리자가 최대 200MB의 MP4·AVI·MOV·WebM 영상을 업로드하면 작업이 `queued`로 생성됩니다. 별도 worker가 `running`으로 작업을 선점하고 프레임별 좌표와 `label`을 추출합니다. 사람이 보이지 않는 프레임도 `-1`로 남깁니다. 기본 최대 처리 프레임 수는 100,000입니다.

학습용 CSV는 16개 특징 열과 `label` 열이 필요합니다. 기존 CSV의 `checkFall`, `checkfall`도 라벨 이름으로 인식합니다. `timestamp` 등 추가 열은 무시합니다. `-1` 데이터는 학습에서 제외합니다. 최소 10개의 유효 행과 정상·낙상 두 클래스가 필요합니다.

자동 생성한 라벨은 사람의 검수를 거쳐 수정하고, 필요한 여러 CSV를 동일 헤더로 합친 뒤 학습에 사용하세요. 영상과 CSV는 사용자별 비공개 경로에 저장합니다. 기존 계정·DB·학습 모델·촬영 영상은 자동 복사하지 않습니다.

### 3. 모델 학습·검증·적용

첫 80%를 학습, 마지막 20%를 검증에 사용하며 정규화 평균·표준편차는 학습 구간에서만 계산합니다. 첫 80%에도 두 클래스가 모두 있어야 합니다. 검증 구간의 클래스 편중 여부를 모델 화면에 표시합니다.

- Dense: 16개 특징 → Dense 32 → Dense 16 → sigmoid
- LSTM: 입력 `(1, 16)` → LSTM 32 → Dense 16 → sigmoid
- 앙상블: Dense 분기와 LSTM 분기를 결합 → Dense 32 → sigmoid

LSTM의 시퀀스 길이는 1이며 여러 프레임의 시간 흐름을 학습하는 구조는 아닙니다. 학습은 기본 20 epochs, 조기 종료를 적용합니다. 정확도·정밀도·재현율과 데이터 수를 저장합니다. 지표 계산의 분류 기준은 0.5이며 실제 감지는 설정된 임계값을 사용합니다.

모델은 Keras 파일과 JSON 정규화 정보·특징 순서를 포함하는 ZIP으로 저장합니다. pickle 업로드를 허용하지 않습니다. 활성화 시 실제 모델 로딩과 추론을 검증합니다. 실시간 감지의 모델 선택은 작성자 또는 지정받은 사용자에게만 허용합니다. 모델 비활성화 또는 사용자 지정 해제 시 진행 중 세션에서도 새 추론을 거부합니다.

### 4. 실시간 감지와 이벤트

HTTPS 또는 localhost에서 브라우저 카메라 권한을 허용해야 합니다. 약 640px 폭의 JPEG를 서버에 전송하고, 응답 후 200ms 뒤 다음 프레임을 전송합니다. 실제 주기는 서버 처리 시간의 영향을 받습니다.

서버는 이미지 크기와 좌표의 유한값을 검증하고 판정합니다. `vr`는 사용자가 보낸 값 대신 visibility로 다시 계산합니다. 기본 규칙 또는 선택한 모델의 결과를 기록합니다. 연속 낙상 의심 조건을 충족하면 이벤트를 생성합니다. 정상·판별 불가 프레임은 연속 횟수를 초기화하고, cooldown 이내에는 새 이벤트를 만들지 않습니다.

세션별 프레임 번호는 증가해야 하며 중복·역순 번호는 HTTP 409로 거부합니다. 종료된 세션 또는 시작 후 8시간이 지난 세션은 새 프레임을 받지 않습니다. 세션 중지와 프레임 기록을 트랜잭션으로 처리합니다. JPEG 원본은 DB나 파일에 저장하지 않으며 관절 좌표·판정만 남깁니다.

감지 설정은 세션·작업 생성 시 스냅샷으로 저장되어 진행 중 설정 변경이 기존 판정에 영향을 주지 않습니다. 카메라 화면을 닫을 때 종료 요청을 시도하지만 네트워크 단절 시 세션은 목록에서 직접 종료할 수 있습니다.

### 5. 기록 확인과 알림

낙상 의심 이벤트 상태는 `미확인 → 확인` 또는 `미확인 → 오탐`입니다. 사용자는 본인의 이벤트에 확인 메모를 남깁니다. XLSX는 본인의 전체 기록을 내보냅니다.

알림이 켜진 사용자에 대해서만 이벤트 생성 시 Telegram 전송 대기열을 만듭니다. 토큰과 Chat ID는 Fernet으로 암호화하며 화면과 감사 로그에 평문을 노출하지 않습니다. 전송은 별도 명령 또는 systemd timer가 처리하며 실패 시 총 3회까지 시도합니다. 실패 로그에는 토큰이 포함된 요청 URL을 저장하지 않습니다.

네트워크 응답 유실 시 Telegram이 수신했어도 실패로 처리되어 재전송될 수 있습니다. 정확히 한 번 전송을 보장하지 않습니다. 알림 worker는 하나만 실행하세요.

## 작업 처리

웹 요청에서 영상 처리나 모델 학습을 실행하지 않습니다. 업로드 뒤 별도 프로세스로 작업 대기열을 처리하세요.

```bash
# 대기 작업을 한 번 처리
uv run --extra vision --extra ml python manage.py process_jobs --once
# 지속적인 작업 처리
uv run --extra vision --extra ml python manage.py process_jobs
# 특정 작업만 처리
uv run --extra vision python manage.py process_video 1
uv run --extra ml python manage.py train_model 2
# 실제 Telegram 메시지 전송
uv run python manage.py send_notifications
```

작업 상태: `queued → running → done / failed`, 대기 작업은 웹에서 취소할 수 있습니다. 이미 선점하거나 종료한 작업은 중복 처리하지 않습니다. worker가 강제 종료되어 `running` 상태에 머무는 경우 실행 프로세스 종료를 확인한 뒤 운영자가 DB 상태를 정리하고 작업을 다시 등록해야 합니다. 실행 중 작업 강제 취소와 자동 재개는 제공하지 않습니다.

## 구조와 경로

```text
config/                    설정·URL·WSGI·ASGI
apps/accounts/             인증 확장 경계 (기본 Django 인증 사용)
apps/core/                 대시보드·감사 로그
apps/menus/                DB 메뉴·그룹·상위 메뉴 권한
apps/detection/            감지·학습·알림 모델, 폼, 서비스, worker
static/                    공통 UI·카메라 JavaScript
templates/                 업무 화면과 로그인
deploy/                    Nginx·systemd 예시
scripts/smoke_optional.py   선택 의존성 실행 확인
```

| 경로 | 용도 |
|---|---|
| `/` | 대시보드 |
| `/accounts/login/`, `/accounts/logout/` | 로그인·POST 로그아웃 |
| `/accounts/password/` | 비밀번호 변경 |
| `/monitor/` | 카메라 감지·세션 목록 |
| `/monitor/start/` | 세션 생성 POST |
| `/monitor/<id>/image/` | JPEG/PNG 입력 POST |
| `/monitor/<id>/frame/` | 좌표 입력 POST |
| `/monitor/<id>/stop/` | 세션 종료 POST |
| `/jobs/`, `/jobs/?kind=train` | 영상·학습 작업 |
| `/models/` | 모델 비교·검증·사용자 지정 |
| `/events/`, `/events/export/` | 이벤트 조회·XLSX |
| `/settings/`, `/notifications/` | 감지 기준·알림 연결 |
| `/admin/` | 시스템 관리 |

좌표 입력 API에는 로그인 세션과 CSRF 토큰이 필요합니다. 예시 요청:

```json
{"sequence": 0, "joints": {
  "left_shoulder_x": 0.3, "left_shoulder_y": 0.7, "left_shoulder_v": 0.9,
  "right_shoulder_x": 0.6, "right_shoulder_y": 0.7, "right_shoulder_v": 0.9,
  "left_knee_x": 0.3, "left_knee_y": 0.9, "left_knee_v": 0.9,
  "right_knee_x": 0.6, "right_knee_y": 0.9, "right_knee_v": 0.9
}}
```

## 운영 배포

1. Ubuntu에 Python 3.12와 uv를 준비하고 `/srv/guardfall2`에 소스를 설치합니다.
2. `guardfall` 서비스 계정을 준비하고 프로젝트·DB·media 쓰기 권한을 부여합니다.
3. `uv sync --frozen --extra vision --extra ml`, `migrate`, `collectstatic --noinput`을 실행합니다.
4. `.env`에서 `DJANGO_DEBUG=false`, 안전한 `DJANGO_SECRET_KEY`, 실제 도메인의 `DJANGO_ALLOWED_HOSTS` 및 `DJANGO_CSRF_TRUSTED_ORIGINS=https://...`를 설정합니다.
5. 신뢰할 수 있는 Nginx가 헤더를 덮어쓰는 구성에서만 `TRUST_PROXY=true`를 설정합니다.
6. 실제 도메인과 TLS 인증서로 `deploy/nginx.conf`를 수정하고 Nginx 설정을 검사합니다.
7. `deploy/guardfall2.service`와 worker 서비스를 설치하고 `daemon-reload` 후 활성화합니다.
8. 알림을 운영할 때만 `notifications.service`·`notifications.timer`를 설치하고 timer를 활성화합니다.
9. 웹 포트 8000은 외부에 공개하지 않고 Nginx의 80/443만 노출합니다.

```bash
uv run --extra vision --extra ml python manage.py check --deploy
uv run --extra vision --extra ml python manage.py collectstatic --noinput
uv run python manage.py test
```

`deploy/` 파일은 설치 예시이며 실제 서버 배포는 별도 수행해야 합니다. 운영 설정의 `check --deploy`에서 HSTS preload 미등록 경고 W021은 남습니다. preload는 도메인별 영향을 검토하고 별도로 설정하세요. 2개 Gunicorn 프로세스와 단일 작업 worker를 기본으로 제안합니다. 카메라 추출은 요청마다 독립 Pose 인스턴스를 생성하여 사용자 간 추적 상태 공유를 방지하지만 처리량은 제한됩니다. 여러 카메라 운영 시 처리 시간·CPU·메모리를 측정하고 별도 추론 서비스로 확장하세요.

### DB 선택

SQLite는 별도 서버 없이 실행됩니다. 여러 동시 카메라·worker를 운영하면 PostgreSQL 전환을 권장합니다.

```bash
uv sync --extra postgres
# .env: DB_ENGINE=postgresql, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT
uv run --extra postgres python manage.py migrate
```

MariaDB는 `DB_ENGINE=mysql`을 사용합니다. Ubuntu에서 `build-essential pkg-config default-libmysqlclient-dev`를 설치한 후 `uv sync --extra mariadb`로 의존성을 설치합니다. DB 전환은 테이블 생성과 데이터 이관을 구분하여 진행하세요. PostgreSQL·MariaDB 서버에서의 실제 검증은 수행하지 않았습니다.

### 백업·복구·모니터링

- DB, `media/`, `.env`와 암호화 키를 함께 백업합니다. 암호화 키를 잃으면 저장된 알림 연결 정보를 복호화할 수 없습니다.
- SQLite 백업은 worker와 웹 쓰기를 중지하거나 SQLite backup API로 일관된 스냅샷을 만듭니다. PostgreSQL은 `pg_dump`, MariaDB는 `mariadb-dump`를 사용합니다.
- 복구 시 서비스를 중지하고 DB·파일·키를 복원한 후 `migrate`, `check`를 실행합니다.
- `journalctl -u guardfall2 -u guardfall2-worker`와 작업 상태, 알림 실패 상태, 디스크 용량을 점검합니다.
- 프레임 기록은 자동 삭제하지 않습니다. 보관 기간·접근 정책을 정하고 운영 용량에 맞춰 삭제 절차를 마련하세요.
- Nginx에 `/media/` 공개 alias를 만들지 않습니다. 파일 다운로드는 인증된 Django 경로를 사용합니다.

## 검증 결과와 한계

- 자동 테스트 44개 통과: 인증·소유자 격리·CSRF·상위 메뉴 권한·모델 사용자 지정·좌표 검증·이벤트 조건·알림 암호화·XLSX·작업 상태·템플릿 렌더링 검증
- 실제 선택 의존성 smoke: 빈 JPEG와 3프레임 영상의 좌표 추출, 합성 CSV에 대한 Dense·LSTM·앙상블 1 epoch 학습·ZIP 저장·재로딩·추론 성공
- 실제 카메라·실제 낙상 영상의 감지 정확도, Telegram 실전 발송, PostgreSQL·MariaDB 서버, 운영 배포는 미검증
- 화면은 템플릿과 JS 구문을 확인했으며, 실제 브라우저 렌더링·모바일·다크 모드 시각 검증은 미실시
- 현재는 연구·시범 운영용 감지 플랫폼입니다. 모델 지표는 업로드 데이터에 한정되며 실제 환경의 안전 성능을 보증하지 않습니다.

```bash
uv run python manage.py test
uv run python manage.py makemigrations --check --dry-run
uv run --extra vision --extra ml python scripts/smoke_optional.py
```

## 라이선스

MIT License. 자세한 내용은 `LICENSE`를 참고하세요.
