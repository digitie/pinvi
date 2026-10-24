## 2026-10-24 — 여섯 프로젝트 npm 보안·버전 정합

- 현재 상태: npm 보안·공통 버전 소스 정합 및 WSL 검증 완료. [버전과 예외](npm-security-alignment-2026-10-24.md). 최종 CI·UI·머지 상태의 정본은 [PR](https://github.com/digitie/pinvi/pull/598)이다.
- 다음 한 작업: 운영 반영을 요청받으면 Manager 정본과 현재 배포 런북에 따라 릴리스를 적용한다. 소스 머지와 운영 배포는 구분한다.

## 2026-10-24 (claude) — `shell-quote` override 보안 수정 (브랜치 `fix/shell-quote-override`)

- 다음 한 작업: draft PR CI green → 리뷰·머지(머지·배포는 소유자). #596(next bump)과 `package-lock.json`·docs가 겹치므로
  나중에 머지되는 쪽을 리베이스하고 lock을 재생성한다.
