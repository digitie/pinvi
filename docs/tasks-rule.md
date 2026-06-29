# tasks-rule.md — Task 문서 작성·유지 규칙

`docs/tasks.md` / `docs/tasks-done.md` 작성 규약의 정본이다. `kor-travel-map`
저장소의 task 분리 정책을 Pinvi 작업 흐름에 맞춰 적용한다.

## 1. 세 문서의 역할

| 문서 | 역할 |
|------|------|
| `docs/tasks.md` | 열린 `[ ]` 진행/예정/보류 백로그와 현재 선점 인덱스 |
| `docs/tasks-done.md` | 완료 `[x]`, 폐기, 머지 history 아카이브 |
| `docs/resume.md` | 현재 진척과 "다음 한 작업" 정본 |

## 2. 분리 규칙

- 완료 task, 머지 이력, 완료 PR 요약, 검증 evidence, 과거 감사 설명은 `tasks.md`에 남기지
  않는다. 완료 후 `tasks-done.md` 상단에 요약 아카이브를 추가하고 `tasks.md`에서는 제거한다.
- 열린 `[ ]`가 하나라도 남은 섹션은 `tasks.md`에 둔다. 전부 닫힌 섹션은
  `tasks-done.md`로 옮긴다.
- 이미 완료·보류가 섞인 legacy 섹션은 별도 정리 task로 나누어 단계적으로 옮긴다.
- 진척 서술은 `resume.md`가 정본이다. `tasks.md`에는 현재 상태 스냅샷을 중복하지
  않고 다음에 실행할 열린 task만 남긴다.
- 현재 진행 중 task도 `tasks.md`에는 task id, 소유자, 브랜치, 충돌 회피 범위만 짧게 남긴다.
  상세 구현 계획과 검증 로그는 `resume.md`, `journal.md`, PR 본문에 둔다.

## 3. Task ID 스킴

- 기본: `T-NNN`
- 하위 작업: `T-NNN<letter>`
- 파생/잔여 작업: `T-NNN-<slug>`
- 이미 `journal.md` / PR / issue에서 참조된 ID는 재번호하지 않는다.

## 4. Status 마커

- `[ ]` 미완료
- `[x]` 완료
- `[~]` 부분 완료
- 완료 항목 안의 해소/철회 표기는 `✅`, `~~취소선~~`을 허용한다.

## 5. Task 분리 기준

다음 중 하나에 해당하면 기존 task를 키우지 말고 새 task로 분리한다.

- API, Web, ETL, infra 중 둘 이상의 경계를 크게 건드린다.
- 별도 ADR 또는 cross-repo 계약 확인이 필요하다.
- 단일 PR에서 검증 시간이 과도하게 길어져 다음 작업 진입을 막는다.
- 구현 중 새 법무/보안/운영 의무가 드러난다.
- N150 live/mutating e2e와 로컬 단위 구현을 분리하는 편이 더 안전하다.

## 6. 신규 Task 진입 전 리뷰 확인

신규 task 진입 전에는 최근 2일 범위의 과거 PR에서 사람 리뷰 코멘트와 inline review
thread를 확인한다. 조치할 코멘트가 있으면 새 task보다 먼저 반영한다.

## 7. 완료 처리 워크플로

Task 완료 기준은 다음 순서다.

1. 구현 또는 문서 변경 완료
2. 로컬 검증과 해당 시 e2e 완료
3. PR 생성
4. PR CI / 필요한 live e2e 확인
5. 머지
6. `docs/tasks-done.md`, `docs/journal.md`, `docs/resume.md` 갱신
7. 다음 task 진입 전 최근 PR 리뷰 코멘트 재확인

## 8. 병행 작업 기록과 충돌 회피

- 신규 task 시작 전 반드시 `git fetch origin main`, `docs/tasks.md`의 `현재 선점 / 충돌 회피` /
  `다음 우선순위` / 열린 후속 섹션, `docs/resume.md`, `docs/journal.md` 최신 항목, 열린
  PR/브랜치를 확인한다.
- 다른 에이전트가 특정 task, 파일, 도메인, PR을 선점 또는 진행 중으로 기록한 경우 같은
  파일/도메인을 바로 수정하지 않는다. 충돌 가능성이 있으면 사용자에게 확인하거나 non-overlap
  task로 전환한다.
- Codex는 새 task 착수 전에 `tasks.md`에 선점 사실과 충돌 회피 범위를 남긴다. 예상 변경 범위와
  검증 계획은 아래 §9 체크리스트를 기준으로 `resume.md` 또는 `journal.md`에 작성하고,
  `tasks.md`에는 예외·충돌 가능성이 있을 때만 짧게 반영한다.
- 완료 후에는 해당 task를 `tasks-done.md`로 옮기고 `tasks.md`에는 열린 항목만 남긴다.
  필요한 경우 `resume.md`와 `journal.md`에도 다음 작업과 검증 결과를 동기화한다.
- 병행 PR이 main에 머지되면 다음 작업 시작 전 `tasks.md` 진행 표기를 최신 main 상태로 갱신한다.
- 문서 운영 규칙처럼 반복 적용되는 내용은 `tasks.md`에 장문으로 두지 않고 본 파일에 옮긴다.

## 9. 새 Task 착수 체크리스트

새 task에 들어갈 때 반복 적용하는 계획 항목은 이 절을 기준으로 한다.

1. 최신 main fetch/rebase 가능 여부와 열린 PR/브랜치 확인.
2. `tasks.md` 현재 선점 / 충돌 회피 섹션 확인 및 선점 기록.
3. `docs/resume.md`, `docs/journal.md` 최신 항목 확인.
4. 관련 ADR/런북/도메인 문서 확인.
5. 코드 수정 전 CodeGraph 영향도 확인.
6. 구현 범위와 검증 계획을 `resume.md` 또는 `journal.md`에 기록.
7. Linux git/개발 환경만 사용하고, Playwright는 N150 runner를 먼저 사용.
