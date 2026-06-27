# Sprint 계획 디렉토리

Pinvi v2 코드 작성 단계 Sprint 계획. 각 Sprint는 별도 markdown으로 박혀
있고, Sprint 진입 시 체크리스트와 함께 검토한다.

| Sprint | 파일 | 상태 | 목표 | 릴리즈 |
|--------|------|------|------|-------|
| Sprint 1 | [SPRINT-1.md](./SPRINT-1.md) | **merged** (PR #9) | 모노레포 scaffolding + DB schema + 핵심 인증 | — |
| Sprint 2 | [SPRINT-2.md](./SPRINT-2.md) | **merged** (PR #10) | 도메인 API + DB (Trip / POI / 4 분리 동의 / Resend / 위치 감사) | — |
| Sprint 3 | [SPRINT-3.md](./SPRINT-3.md) | **merged** (PR #11) | Admin 콘솔 + RBAC + audit chain + seed | — |
| Sprint 4 | [SPRINT-4.md](./SPRINT-4.md) | **released** (`v0.1.0`, 2026-06-13) | 지도 UI + `vworld-map-web` + 라이브 feature read + **CI/CD 재활성** | **`v0.1.0`** |
| Sprint 5 | [SPRINT-5.md](./SPRINT-5.md) | in progress (Admin/ETL/Grafana/System + WebSocket client 1차 post-v0.1.0 반영) | 실시간 WebSocket + Dagster ETL + Loki + Grafana embed + **Backup/Restore 1차** | **`v0.2.0`** |
| Sprint 6 | [SPRINT-6.md](./SPRINT-6.md) | proposed | 일정 최적화 + LBS 신고 + 법무 + **MCP 외부 인터페이스** + **Backup UI 핫스왑** + **Korean geofencing** + **T108 N150 병행 배포** | **`v1.0.0`** |

> **상태 정합 주의 (감사 P-04, 2026-06-06 / T-150 반영)**: Sprint 5/6 항목 일부
> (T-067 KASI, T-109 geofencing, T-110 Grafana, T-115 backup foundation)는 Sprint 4
> 중 선반영됐다. 개별 SPRINT-N.md 헤더와 본 표는 같은 상태를 가리키도록 정리했다.

## 릴리즈 마일스톤

| 버전 | 시점 | 핵심 기능 |
|------|------|----------|
| `v0.1.0` | Sprint 4 종료 | 지도 + 여행 + Admin 기본 기능 가능. **출시 게이트(DEC-06, 2026-06-06 확정)**: 라이브 feature read(kor_travel_map HTTP 연동, T-066/ADR-027) 충족. snapshot-only 조기출시 금지 조건 해소. 2026-06-13 tag + GitHub Release 완료. |
| `v0.2.0` | Sprint 5 종료 | 실시간 + ETL + 운영 가시화 (Grafana). Backup/Restore 1차 (script + endpoint, UI는 v1.0). |
| `v1.0.0` | Sprint 6 종료 | 외부 정식 출시. MCP 외부 인터페이스 + Backup 핫스왑 UI + Korean geofencing + Odroid+N150 양 노드 + LBS 신고 + 법무 4 문서. |
| `v1.1.0+` | post-Sprint 6 | PWA / 푸시 알림 / 사진 업로드 / `kor-travel-concierge` 통합 |

SPEC V8 #5 (P장)와 정합. **Sprint 3 (Admin)이 Sprint 4 (지도)보다 앞** — 데이터
흐름 검증 후 지도 작업 (원본 결정).

자세한 SPEC V8 6편 적용 노트는 `docs/spec/v8/`.

## Sprint 진입 게이트 (공통)

각 Sprint 진입 PR은 다음을 확인:

- 이전 Sprint의 DoD 모두 충족
- 신규 Sprint의 ADR들이 `proposed` → `accepted` 전환 (시기 의존 ADR만 해당)
- 직전 Sprint에서 발견된 회귀/burndown 정리 완료
- `kor-travel-map`의 대응 Sprint(별 저장소) 진척도와 OpenAPI 계약 확인

## 관련 ADR

- **ADR-001** — v1 보존 + v2 재시작
- **ADR-002** — 함수 직접 호출 모델(ADR-026으로 superseded)
- **ADR-003** — schema 책임 분담
- **ADR-005** — provider 어댑터 wrapper 금지
- **ADR-006** — Dagster code location 분리
- **ADR-007** — PR-only workflow
- **ADR-015** — Kakao Maps SDK 폐기 + VWorld/MapLibre 채택
- **ADR-046** — Web 지도 클라이언트 `vworld-map-web` 전환
- **ADR-017** — CodeGraph + agent별 고정 worktree
- **ADR-018** — 한국 전용 geofencing
- **ADR-019** — MCP 외부 인터페이스
- **ADR-020** — AI companion 별도 repo 분리
- **ADR-021** — GitHub Actions CI/CD 재활성화
- **ADR-022** — Backup / Restore 핫스왑 정책
- **ADR-023** — Odroid M1S + N150 병행 운영
- **ADR-024** — NTFS worktree + WSL ext4 테스트 미러
- **ADR-025** — geocoding은 kor-travel-geo v2 REST 직접
- **ADR-026** — Pinvi ↔ `kor-travel-map` OpenAPI HTTP 계약
- **ADR-027** — kor-travel-map 운영급 HTTP 서비스 신설 대기
- **ADR-028** — 정규 `feature_id` 포맷
- **ADR-029** — `notice_plans` 명칭 충돌 해소
- **ADR-030** — 외부 API 규약 정본
- **ADR-031** — POI soft delete + nullable `feature_id`
- **ADR-036** — Curated trip plan POI nullable feature link + 외부 feature-backed upsert
- **ADR-041** — Expo `apps/mobile` 구조 스캐폴드
- **ADR-043** — 모바일 Expo Dev Client + EAS Build 기준선

## 참조

- Backlog 전체: `../tasks.md`
- 진척도: `../resume.md`
- 작업 일지: `../journal.md`
- 책임 경계: `../architecture.md`
- 라이브러리 통합: `../kor-travel-map-integration.md`
