# Stockholm BRF Alert Agent

스톡홀름 도심(Innerstad) BRF 아파트 매물을 모니터링하고, 아래 조건에 맞는 **신규 매물**이 올라오면 알림을 보내는 에이전트입니다.

- 매매 후 전체 세입자(2차 임대, andrahandsuthyrning) 가능성
- 분리 현관/분리 출입구(uthyrningsdel, separat ingång 등) 기반 부분 임대 가능성

> 주의: 본 프로젝트는 **키워드 기반 후보 탐지** 도구입니다. 실제 임대 허용 여부는 BRF 정관, 이사회 승인, 시점별 규정에 따라 달라지므로 계약 전 반드시 직접 확인해야 합니다.

## 기능 요약

- Hemnet 검색 결과 페이지 모니터링
- 신규 매물만 상세 조회 (중복 방지: SQLite 상태 저장)
- BRF/도심 키워드 + 임대 가능 키워드 규칙 매칭
- Slack 웹훅 / SMTP 이메일 알림 지원
- 단발 실행(run once) 또는 데몬 모드(주기 실행)

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## 설정

샘플 설정 파일:

```bash
cp config.example.yaml config.yaml
```

`config.yaml`에서 확인할 항목:

1. `sources[].search_urls`: Hemnet에서 직접 필터링한 검색 URL
2. `matching.*keywords`: 임대 가능성 판정 키워드
3. `notifications.slack` 또는 `notifications.email`: 알림 채널

환경변수 참조(`${ENV_NAME}`)를 지원합니다.

예:

```bash
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
export SMTP_USERNAME="..."
export SMTP_PASSWORD="..."
```

## 실행

단발 실행:

```bash
brf-alert-agent --config config.yaml run
```

또는:

```bash
python -m brf_alert_agent --config config.yaml run
```

데몬 모드:

```bash
brf-alert-agent --config config.yaml daemon
```

## 테스트

```bash
pytest
```

## 운영 팁

- 처음 실행 시 기존 매물도 "신규"로 간주될 수 있으니, 알림 채널 확인 후 운영하세요.
- 더 보수적으로 필터링하려면 `innerstad_keywords`, `whole_unit_rental_keywords`, `separate_entrance_keywords`를 좁히세요.
- 여러 소스 URL(예: 지역별 검색 URL)을 `sources[0].search_urls`에 추가하면 병합 모니터링합니다.
