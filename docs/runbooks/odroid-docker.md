# Odroid 실행 경로 퇴역 안내

이 문서는 역사적 참고용으로만 남겨 둔다. ADR-067에 따라 Odroid M1S는 Pinvi의
실행·배포·복구·UPS 제어 대상에서 영구 퇴역했다.

다음 작업은 수행하지 않는다.

- Odroid에서 API/Web/Dagster 실행 또는 재기동
- Odroid DB/RustFS 복구와 public traffic 전환
- Odroid doctor, raw Compose, fallback deployment 실행
- Odroid를 대상으로 한 UPS shutdown hook 설치

현재 staging/production 실행 대상은 N150 하나이며, 배포·복구·live UI 검증은
[`deploy.md`](./deploy.md)와 N150 manager/Playwright runner를 따른다.
ARM64 관련 과거 설계·Sprint 기록은 역사 기록으로 보존한다.
