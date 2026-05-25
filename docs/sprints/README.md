# Sprint 계획 디렉토리

TripMate v2 코드 작성 단계 Sprint 계획. 각 Sprint는 별도 markdown으로 박혀
있고, Sprint 진입 시 체크리스트와 함께 검토한다.

| Sprint | 파일 | 상태 | 목표 |
|--------|------|------|------|
| Sprint 1 | [SPRINT-1.md](./SPRINT-1.md) | **proposed** (사용자 진입 승인 대기) | 모노레포 scaffolding + DB schema + 핵심 인증 |
| Sprint 2 | (작성 예정) | proposed | 사용자 도메인 (Trip / POI 첨부) + 라이브러리 최소 연계 |
| Sprint 3 | (작성 예정) | proposed | Admin 콘솔 + Notice plan + Storage API |
| Sprint 4 | (작성 예정) | proposed | Dagster asset 통합 + 첫 provider 적재 검증 |
| Sprint 5 | (작성 예정) | proposed | UI 완성도 + Telegram/Gemini/Resend + Odroid 배포 |

순서는 잠정안. 사용자 review 후 SPRINT-N.md를 한 건씩 박는다.

## Sprint 진입 게이트 (공통)

각 Sprint 진입 PR은 다음을 확인:

- 이전 Sprint의 DoD 모두 충족
- 신규 Sprint의 ADR들이 `proposed` → `accepted` 전환 (시기 의존 ADR만 해당)
- 직전 Sprint에서 발견된 회귀/burndown 정리 완료
- `python-krtour-map`의 대응 Sprint(별 저장소) 진척도 확인 (라이브러리 의존 핀)

## 관련 ADR

- **ADR-001** — v1 보존 + v2 재시작
- **ADR-002** — TripMate ↔ `python-krtour-map` 함수 호출
- **ADR-003** — schema 책임 분담
- **ADR-005** — provider 어댑터 wrapper 금지
- **ADR-006** — Dagster code location 분리
- **ADR-007** — PR-only workflow

## 참조

- Backlog 전체: `../tasks.md`
- 진척도: `../resume.md`
- 작업 일지: `../journal.md`
- 책임 경계: `../architecture.md`
- 라이브러리 통합: `../krtour-map-integration.md`
