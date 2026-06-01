# 문서 충돌 정정 실행 계획 — 2026-06-02

## 목적

최신 `origin/main` 기준 문서를 다시 훑어 ADR-024(개발 환경), ADR-015(지도
클라이언트), ADR-025(geocoding 경계)와 충돌하는 잔여 문구를 정정한다.

## 범위

- 진입/작업 문서: `README.md`, `AGENTS.md`, `SKILL.md`, `docs/agent-guide.md`
- 개발 환경/runbook: `docs/runbooks/local-dev.md`, `docs/runbooks/README.md`,
  `docs/runbooks/etl.md`, `docs/conventions/{coding-style,testing}.md`
- 아키텍처/API/Sprint: `docs/architecture.md`, `docs/api/features.md`,
  `docs/sprints/SPRINT-1.md`, `docs/sprints/SPRINT-4.md`,
  `docs/spec/v8/00-infrastructure.md`
- 추적 문서: `docs/journal.md`, `docs/resume.md`, `docs/tasks.md`

## 반영 기준

- git/편집/commit/push는 NTFS worktree + Windows `git.exe`.
- WSL ext4는 테스트/Docker/의존성 전용 일회용 미러, commit/push 금지.
- 지도 UI는 `maplibre-vworld-js` 직접 import. TripMate 전용 wrapper 패키지 금지.
- 사용자 대면 주소/좌표/행정구역 검색은 `kraddr-geo` v2 REST 직접 호출.

## 검증

- stale 문구 `rg` 검색: 완료.
- `git diff --check`: 통과.
- Markdown lint: `npx markdownlint-cli2 "README.md" "AGENTS.md" "CLAUDE.md"
  "SKILL.md" "docs/**/*.md"` 실행. 저장소 기존 스타일 위반(테이블 spacing, 80자
  제한 등) 1,977건으로 실패. 이번 PR 범위 밖의 기존 문서 스타일 부채로 보고
  별도 정리 필요.
- 신규 파일 `docs/execplan/doc-review-2026-06-02.md` 단독 markdownlint: 통과.
- 코드 테스트: 문서 전용 변경이라 생략.
