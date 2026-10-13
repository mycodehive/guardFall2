# GuardFall2 개발·확장 가이드

생성일: 2026-10-14. Python 3.12, Django 5.2, uv, SQLite 기본 구성입니다.

## 확장 경계

- `config`: 환경변수, DB 선택, 인증·CSRF·보안 미들웨어
- `apps/accounts`: 기본 Django 인증 확장용 앱 경계
- `apps/core`: 대시보드, 감사 로그
- `apps/menus`: 3단 DB 메뉴와 그룹·상위 권한
- `apps/detection`: 감지 설정·좌표·이벤트·작업·모델·알림

새 업무 기능은 별도 앱에 추가하고 마이그레이션으로 고유 메뉴 코드를 등록합니다. 뷰에서 `@feature('code')`를 적용하고 데이터 소유자 조건을 검사합니다. 소유자가 있는 파일은 인증된 다운로드 뷰로 제공하세요.

## UI

`templates/base.html`에서 공유 레이아웃과 `content`, `title`, `extra_js` 블록을 제공합니다. 스타일은 `static/css/base.css`, 동작은 `static/js/platform.js`입니다. `.card`, `.page-heading`, `.button`, `.secondary`, `.danger`, `.table-wrap`, `.tabs` 클래스를 사용합니다. 로컬 CSS를 사용하므로 외부 CDN 없이 공통 화면이 표시됩니다.

색상: 헤더 `#11283e`, 사이드바 `#1a2f4a → #0f2035`, 바탕 `#f3f5f7`, 기본 버튼 `#0f4a8a`, 보조 `#4f6a86`, 삭제 `#bd3941`. 다크 모드는 CSS 변수와 `guardfall2.theme` localStorage를 사용합니다.

## 환경설정·연결

`.env.example`에는 부트스트랩 비밀값과 DB 정보의 자리표시자만 포함합니다. `/settings/`에서 공통 판정값을 변경하고 `/notifications/`에서 내 알림 연결을 변경합니다. 서버 암호화 키를 Git에 저장하지 마세요.

## 검증 및 배포

```bash
uv sync --frozen
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py test
uv run python manage.py makemigrations --check --dry-run
```

영상·학습 설치와 운영 절차는 README 및 `deploy/` 예시를 참고합니다. 학습 입력 특징을 바꾸면 `ml.FEATURES`, CSV 검증, 모델 manifest와 추론을 함께 변경하고 이전 모델 호환성을 명시적으로 처리하세요.

소스에 미구현 TODO는 없습니다. 실제 카메라·낙상 영상 검증, 실제 브라우저 시각 QA, 서버 DB/배포 검증, 자동 데이터 보관 정책, 모델 버전 승격·폐기, 강제 종료 작업 복구는 확장 과제입니다.
