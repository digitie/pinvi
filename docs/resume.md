## 2026-10-24 — 여섯 프로젝트 npm 보안·버전 정합

- 현재 상태: npm 보안 갱신·여섯 프로젝트 버전 정합 후보. [버전과 예외](npm-security-alignment-2026-10-24.md).
- 다음 한 작업: WSL/CI·두 독립 리뷰·N150 후보 UI 검증을 완료하고 PR을 머지한다. 운영 배포는 별도다.

## 2026-10-24 (claude) — `shell-quote` override 보안 수정 (브랜치 `fix/shell-quote-override`)

- 다음 한 작업: draft PR CI green → 리뷰·머지(머지·배포는 소유자). #596(next bump)과 `package-lock.json`·docs가 겹치므로
  나중에 머지되는 쪽을 리베이스하고 lock을 재생성한다.
