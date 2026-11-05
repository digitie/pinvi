# #658 복원 cleanup과 advisory lock 해제 경합

## 범위와 기준

- 기준: `ff5c2386c22412714b42365fd3ab801502258087`, 브랜치 `agent/codex-658-hotswap-lock-release`.
- 소유: `scripts/restore-hotswap.sh`, 직접 관련 helper·통합 검사·복원 문서.
- 최신 #658 본문과 댓글 없음 확인. 초기 script blob `5497b7172324bcdac0825a4284d996661fb13aa9`, 통합 검사 blob `ded7a61e3e5ed8dacfb50fd0cd766119e0127ac0`.
- 운영·SSH·실제 prod·Telegram 접근 금지. 다른 작업자 변경과 보호 stash를 보존하고 봉인된 migration은 수정하지 않는다.
- 새 main 통합·ready 전환·merge는 하지 않는다. 전문적 적대 리뷰 2인은 메인 담당이다.

## 진행

1. [x] 별도 Linux worktree 생성, 지침·복원 런북 및 Linux native CodeGraph explore/impact 확인.
2. [x] 이 한국어 계획을 감사 후 commit/push하고 draft PR을 먼저 생성한다.
3. [x] 소유 disposable PostgreSQL 18에서 기존 경합을 실패 우선으로 재현한다. 정확히 소유한 backend를 식별하고 클라이언트 종료와 서버 lock 정리를 결정적으로 분리한다.
4. [ ] 재현된 경우에만 최소 변경한다. 해제 확인이 필요하면 서버 상태를 직접 확인하고 시간을 제한한다.
5. [ ] 기존 timeout·실패 status·signal cleanup·자격 출력 억제·DB fencing 불변식을 회귀 검증한다.
6. [ ] PG·lint·source hash·한계를 기록하고 정확 SHA의 완성 draft PR을 메인에 인계한다.

## 검증 원칙

무한 재시도나 기존 기대값 완화로 실패를 숨기지 않는다. PID만으로 다른 세션을 종료하지 않으며 exact 본인 backend 식별이 없으면 서버 세션 정리 mutation을 하지 않는다. 소스가 이미 보완되었거나 재현할 수 없으면 새 제품 코드를 만들지 않고 근거를 보고한다. 각 commit 직전 현재 worktree에서 지정 `audit-staged.py`를 실행한다. 병행 서브에이전트는 읽기 전용 재현·위험 검토를 맡고 최종 2인 전문 리뷰를 대체하지 않는다.

## 실패 우선 근거

- 기존 canonical PG18 검사는 1통과(11.35초).
- 실제 runner의 lock 획득·cleanup 함수를 소유 PG18에서 실행하고 해당 backend를 SIGSTOP한 신규 회귀는 기존 script에서 1실패(6.69초): cleanup이 서버 정리 전 상태 0으로 반환했다.
- 기존 즉시 lock 부재 단언은 그대로 유지한다. 병행 읽기 전용 검토는 fence URL·전체 deadline·원래 status·타 세션 비간섭을 지적했다.
