# KTO TourAPI 운영 Runbook

## 목적

KTO TourAPI 연동은 한국관광공사 공공 관광정보를 여행지 후보와 주변 추천 신호로 사용하기 위한 경계다. TripMate backend는 별도 adapter/gateway를 만들지 않고 `pykrtourapi`를 직접 사용한다.

## 로컬 설정

`apps/api/.env`에 아래 값을 둔다. 실제 인증키는 커밋하지 않는다.

```bash
TRIPMATE_KTO_SERVICE_KEY=공공데이터포털_decoding_인증키
TRIPMATE_KTO_MOBILE_APP=TripMate
TRIPMATE_KTO_MOBILE_OS=WEB
TRIPMATE_KTO_TIMEOUT_SECONDS=10
TRIPMATE_KTO_MAX_RETRIES=2
```

의존성은 WSL2에서 설치한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && pip install -e ."
```

## 검증

KTO 계약 테스트는 실제 외부 API를 호출하지 않는다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && pytest -q tests/test_kto_pykrtourapi.py"
```

전체 backend 검사:

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && ruff check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && ruff format --check ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && mypy ."
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && pytest -q"
```

## 수동 smoke 예시

운영 키가 있는 로컬 환경에서만 실행한다. 출력에는 인증키가 포함되지 않게 한다.

```bash
wsl.exe -e bash -lc "cd /mnt/f/dev/mapplan/apps/api && . .venv-wsl/bin/activate && python - <<'PY'
from app.core.kto import build_kto_kor_client
from pykrtourapi import Wgs84Coordinate

client = build_kto_kor_client()
page = client.location_based_list(
    coordinate=Wgs84Coordinate(longitude=126.9769, latitude=37.5796),
    radius=15000,
    num_of_rows=3,
)
print({'total_count': page.total_count, 'items': [item.title for item in page.items]})
print({'endpoint': page.endpoint, 'params': page.request_params})
PY"
```

## 장애 대응

- `TourApiAuthError`: `TRIPMATE_KTO_SERVICE_KEY` 누락, 잘못된 key, data.go.kr 권한 문제를 확인한다.
- `TourApiRateLimitError`: 호출 빈도를 줄이고, 같은 `Page.request_params`에 대한 cache hit 여부를 확인한다.
- `TourApiServerError`: upstream 장애로 기록하고 재시도 후에도 실패하면 사용자에게 일시 오류를 표시한다.
- `TourApiParseError`: TourAPI 응답 schema drift 가능성이 있으므로 raw payload를 보존하고 `pykrtourapi` 이슈로 upstream한다.
- 모든 `TourApiError` 계열은 가능한 경우 `metadata`에 `result_code`, `status_code`, `endpoint`, `service_name`, `failure_kind`를 담는다. 인증키 원문은 metadata나 메시지에 남기지 않는다.

## 변경 절차

1. `pykrtourapi`에서 필요한 기능을 먼저 구현하거나 commit을 확인한다.
2. `apps/api/pyproject.toml`의 `pykrtourapi` commit을 갱신한다.
3. `tests/test_kto_pykrtourapi.py`에서 새 공개 계약을 검증한다.
4. `docs/api/kto-tourapi.md`, `docs/data-sources.md`, `docs/decisions/20260506-pykrtourapi-client-boundary.md`를 갱신한다.
5. WSL2에서 검증 명령을 실행한다.

## 주의 사항

- `pykrtourapi`는 GPL-3.0-or-later다. 배포 정책 확정 전에 라이선스 영향을 별도 확인한다.
- `TarRlteTarService1` 결과는 `build_kto_hub_client().related_tour` typed helper를 우선 사용한다. 아직 typed helper가 없는 TourAPI 서비스가 필요하면 TripMate에 래퍼를 만들지 말고 `pykrtourapi`에 upstream한다.
- KTO `KorService2` 전체 응답 저장 예외는 KTO raw/serving/snapshot 테이블에만 적용한다.
