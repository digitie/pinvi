# tasks-rule.md — Task 문서 작성·유지 규칙

`docs/tasks.md` / `docs/tasks-done.md` 작성 규약의 정본이다. `kor-travel-map`
저장소의 task 분리 정책을 Pinvi 작업 흐름에 맞춰 적용한다.

## 1. 세 문서의 역할

| 문서 | 역할 |
|------|------|
| `docs/tasks.md` | 열린 `[ ]` 진행/예정/보류 백로그와 상단 인덱스 |
| `docs/tasks-done.md` | 완료 `[x]`, 폐기, 머지 history 아카이브 |
| `docs/resume.md` | 현재 진척과 "다음 한 작업" 정본 |

## 2. 분리 규칙

- 완료 task를 `tasks.md`에 길게 남기지 않는다. 완료 후 `tasks-done.md` 상단에
  요약 아카이브를 추가하고 `tasks.md`에서는 제거한다.
- 열린 `[ ]`가 하나라도 남은 섹션은 `tasks.md`에 둔다. 전부 닫힌 섹션은
  `tasks-done.md`로 옮긴다.
- 이미 완료·보류가 섞인 legacy 섹션은 별도 정리 task로 나누어 단계적으로 옮긴다.
- 진척 서술은 `resume.md`가 정본이다. `tasks.md`에는 현재 상태 스냅샷을 중복하지
  않고 다음에 실행할 열린 task만 남긴다.

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
