# Sprint 4까지 PR 리뷰·수정·머지 runbook

## 목적

Sprint 4 완료 전까지 새 PR이 올라오면 단순 승인/반려가 아니라 다음 흐름을 반복한다.

1. PR 변경분을 리뷰한다.
2. 상세 코멘트를 남긴다.
3. 필요한 코드를 직접 수정한다.
4. 기반 라이브러리 변경이 더 올바르면 해당 라이브러리 PR을 먼저 만들고 머지한다.
5. Pinvi 의존 핀 또는 호출부를 동기한다.
6. 검증을 통과한 뒤 Pinvi PR을 머지한다.

`docs/sprints/SPRINT-4.md`의 DoD가 충족되어 Sprint 4 종료 PR이 머지되면 이 runbook의
지속 운영 여부를 다시 결정한다.

## 적용 범위

- Pinvi 본 저장소의 모든 새 PR과 `ready_for_review` 전환 PR
- `.github/workflows/codex-pr-review.yml`의 PR 이벤트와
  `.github/workflows/codex-pr-monitor.yml`의 예약/수동 열린 PR 감시 결과
  (외부 API key 없는 MCP 기반 review reminder)
- Sprint 1~4 목표에 직접 영향을 주는 기반 라이브러리 PR
- 특히 다음 저장소와의 경계:
  - `kor-travel-map`
  - `maplibre-vworld-react`
  - `python-kraddr-base`, `kor-travel-geo`, `python-kraddr-gop`
  - 공공 API provider 라이브러리 (`python-kma-api`, `python-visitkorea-api` 등)

## 원칙

- 변경량 최소화보다 장기 설계 정합성을 우선한다.
- 단, Sprint 1~4 목표와 무관한 추상화·대규모 재작성은 별도 ADR 또는 후속 backlog로
  분리한다.
- Pinvi가 소유하지 않는 책임은 Pinvi wrapper로 숨기지 않는다. 소유 라이브러리를
  수정하고 PR → 머지 → Pinvi sync 순서로 처리한다.
- `main` 직접 push는 금지한다. 모든 변경은 feature branch + PR로 간다.
- merge는 상태 검사, 문서 갱신, 필요한 라이브러리 sync가 끝난 뒤 수행한다.

## 리뷰 절차

1. `AGENTS.md`, `SKILL.md`, `docs/agent-guide.md`, 관련 Sprint 문서를 먼저 확인한다.
2. `git diff base...head`로 PR 변경분만 본다.
3. 다음 순서로 찾는다.
   - 버그, 보안, 데이터 손실, 권한 우회
   - ADR·Sprint 목표·책임 경계 위반
   - 테스트 누락 또는 검증 불가능한 변경
   - 기반 라이브러리에 있어야 할 코드가 Pinvi에 들어온 경우
   - Sprint 4 지도/UI 흐름을 어렵게 만드는 단기 설계
4. PR에 상세 코멘트를 남긴다. 코멘트는 아래 구조를 기본으로 한다.

```markdown
## 리뷰 결과

### 차단 이슈
- ...

### 설계 보강 제안
- ...

### 필요한 코드 수정
- ...

### 기반 라이브러리 sync
- ...

### 검증
- ...

### 머지 판단
- ...
```

차단 이슈가 없으면 그 사실과 남은 위험만 명확히 적는다.

## 지속 감시 방식

- `.github/workflows/codex-pr-review.yml`은 `opened` / `ready_for_review` /
  `reopened` / `synchronize` 이벤트에서 대상 PR 하나를 즉시 조회한다.
- `.github/workflows/codex-pr-monitor.yml`은 5분 cron과 `workflow_dispatch`에서 열린 PR
  전체를 조회한다. GitHub schedule은 실제 실행 간격이 지연될 수 있으므로 PR 이벤트
  workflow가 1차 신호, monitor가 보정 신호다.
- 두 workflow는 같은 `scripts/pr_review_monitor.py`를 사용한다.
- draft PR은 건너뛴다.
- PR 최신 head SHA에 `pr-review-reminder:head=<sha>` 마커가 달린 알림 코멘트가
  있으면 건너뛴다.
- 새 PR, `ready_for_review` PR, 또는 새 commit이 올라와 head SHA가 바뀐 PR은 다시
  리뷰 필요 알림을 남긴다.
- GitHub Actions에서 외부 LLM API key를 사용하지 않는다. `OPENAI_API_KEY`는 등록하지
  않으며, workflow는 `openai/codex-action`을 호출하지 않는다.
- 알림 본문은 `kor-travel-map`과 같은 MCP 진입 방식을 명시한다.
  `.codex/config.toml`, `claude.json`, `antigravity.json`, `.gemini/mcp.json`에서
  CodeGraph / Playwright / Sequential Thinking / Telegram MCP 설정을 확인하고,
  변경 심볼은 CodeGraph 영향도 확인을 우선한다.
- 실제 리뷰는 알림 댓글을 본 에이전트 또는 사람이 본 runbook 기준으로 수행하고,
  findings / 필요한 수정 / 검증 / 머지 판단을 PR에 별도 코멘트로 남긴다.

## 코드 수정 절차

1. PR branch에 push 권한이 있으면 같은 branch에서 수정한다.
2. 권한이 없거나 외부 기여자 branch면 `agent/<id>/<topic>` branch를 만들고 후속 PR을
   연다.
3. 수정은 테스트를 먼저 보강한 뒤 구현한다.
4. 여러 서비스·DB schema·라이브러리 경계를 건드리면 `docs/execplan/<task-name>.md`를
   먼저 작성하거나 갱신한다.
5. 의미 있는 변경은 `docs/journal.md`, `docs/resume.md`, 필요 시 `docs/tasks.md`,
   `docs/decisions.md`를 함께 갱신한다.

## 기반 라이브러리 sync 절차

Pinvi 코드가 다음 일을 하려 한다면 Pinvi PR을 멈추고 소유 라이브러리부터 고친다.

- 지도 feature 정규화, `feature_id`, `SourceRecord`, `feature`/`provider_sync` DDL
- provider raw → DTO 변환
- VWorld/MapLibre 공통 지도 컴포넌트, marker clustering, polygon/route primitive
- 한국 행정구역·주소·지오코딩 base 데이터
- 공공 API client의 parsing, retry, pagination, error model

기반 라이브러리 수정 순서:

1. 라이브러리 저장소에서 feature branch를 만든다.
2. 라이브러리 테스트와 문서를 함께 갱신한다.
3. 라이브러리 PR을 열고 리뷰 후 머지한다.
4. Pinvi에서 의존 SHA/version을 갱신한다.
5. Pinvi 호출부와 문서를 sync한다.
6. 양쪽 PR 링크를 서로 남긴다.

## 검증 기준

- 백엔드: `pytest`, `ruff`, `mypy`, OpenAPI drift, DB 변경 시 Alembic + EXPLAIN
- 프론트엔드: WSL ext4 미러에서 dev server / lint / typecheck / build / Vitest를
  실행한다. Playwright 기반 브라우저 e2e와 주요 viewport screenshot만 Windows
  Node/브라우저에서 실행한다.
- ETL: Dagster asset dry-run, provider fixture, idempotency 확인
- 지도/UI: `maplibre-vworld-react` 책임인지 Pinvi 책임인지 먼저 확인하고, 브라우저에서
  실제 rendering을 확인한다.
- Playwright 예외를 제외한 실행 명령은 WSL ext4 미러에서 실행하고, NTFS 작업본과
  sync 상태를 보고한다.

## 머지 기준

- 차단 리뷰 코멘트가 모두 해결됨
- 필요한 기반 라이브러리 PR이 머지되고 Pinvi가 sync됨
- 관련 문서·journal·resume 갱신 완료
- CI 또는 로컬 대체 검증 결과가 PR 본문/코멘트에 기록됨
- Squash merge를 기본으로 하되, 의미 있는 commit stack이면 rebase merge를 선택할 수 있음
