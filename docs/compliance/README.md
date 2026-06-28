# 컴플라이언스

위치정보법 + PIPA 2024 + 외부 provider TOS 점검 매트릭스. SPEC V8 #0 O장 정합.

## 1. 인덱스

| 파일                                                                               | 범위                                                         |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| [lbs-act.md](./lbs-act.md)                                                         | 위치정보법 (LBS 신고 + 별도 동의 + 6개월 감사 로그)          |
| [pipa.md](./pipa.md)                                                               | 개인정보보호법 2024 (과징금 + 침해 통지 + Privacy by Design) |
| [data-policy.md](./data-policy.md)                                                 | 외부 provider 데이터 정책 (VWorld/Naver/Google/Juso 등)      |
| [legal-ops-review-gap-crosswalk.md](../execplan/legal-ops-review-gap-crosswalk.md) | PR 리뷰 legal/ops gap → Task 매핑 정본                       |

## 2. 책임 / 출시 직전 체크 (Sprint 6)

- [ ] **LBS 사업자 신고** 완료 (방통위 LBSC) — `lbs-act.md`
- [ ] **법무 4 문서**: 이용약관 / 처리방침 / LBS 약관 / 위치 동의 — 변호사 검토
- [ ] PIPA 침해 자동 트리거 가동 — `pipa.md`
- [ ] provider 위탁자 명시 처리방침에 포함
- [ ] Privacy by Design 체크리스트 PR 템플릿 통합
- [ ] CPO 역할 부여 + `location_access_log` SELECT 권한

## 3. Daily

- `app.admin_audit_log` chain 점검 (스크립트화 — `docs/runbooks/admin.md` §5)
- `app.location_access_log` chain
- Sentry/Loki PII 마스킹 동작 확인 (`docs/integrations/sentry.md`)
