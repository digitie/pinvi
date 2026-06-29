# docs/legal — 법무 문서 (초안, 변호사 검토 전)

Pinvi v1.0 출시에 필요한 법무 4문서의 **초안(placeholder)**이다. 모든 문서는 **변호사 검토
전**이며 법적 효력이 없다. 시행일·사업자 정보·관할은 출시 직전 확정한다(T-274).

| 문서 | 파일 | 동의 type | 웹 경로 |
|---|---|---|---|
| 이용약관 | `terms-of-service.md` | `tos` | `/legal/terms-of-service` |
| 개인정보 처리방침 | `privacy-policy.md` | `privacy` | `/legal/privacy-policy` |
| 위치기반서비스 이용약관 | `lbs-terms.md` | `lbs_tos` | `/legal/lbs-terms` |
| 개인위치정보 수집·이용 동의 | `location-consent.md` | `location_collection` | `/legal/location-consent` |

## 정본 / 동기

- 본 `.md`가 법무 검토용 **작업 정본**이다.
- 웹 렌더 콘텐츠는 `apps/web/lib/legalDocs.ts`(구조화 데이터)로, 동의 UX(`settings/consents`,
  `profile-complete`)가 `/legal/<slug>`로 링크한다. 초안 단계에서는 두 곳을 함께 갱신하고,
  변호사 확정본이 나오면 본 `.md`를 기준으로 웹 콘텐츠를 일괄 교체한다.
- 운영 표면(PIPA incident/DSR/retention/suppression/moderation, 동의 기록/철회)은 T-275~282로
  이미 구현됐다. 본 task(T-269)는 **문서 + 동의 UX 링크**다.

## 검토 체크리스트 (출시 전)

- [ ] 변호사 검토 완료 (각 문서 `[변호사 검토 필요]` 마커 제거)
- [ ] 사업자/대표/주소/연락처/CPO 실제 정보 기입 (공개 repo에는 placeholder 유지 — ADR-047)
- [ ] 시행일 확정 + 공지(개정 시 7일/불리한 변경 30일 사전 공지)
- [ ] 위치기반서비스사업 신고(방통위) 번호 기입 (`docs/compliance/lbs-act.md`)
- [ ] 개인정보 처리방침 ↔ 실제 처리 항목/보유기간/수탁사 정합 (`docs/compliance/pipa.md`)

## 참조

- `docs/compliance/lbs-act.md` (위치정보법 신고·의무)
- `docs/compliance/pipa.md` (개인정보보호법 점검)
- `docs/compliance/data-policy.md`
