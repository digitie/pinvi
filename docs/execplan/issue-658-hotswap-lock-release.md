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
4. [x] 재현된 경우에만 최소 변경한다. 해제 확인이 필요하면 서버 상태를 직접 확인하고 시간을 제한한다.
5. [x] 기존 timeout·실패 status·signal cleanup·자격 출력 억제·DB fencing 불변식을 회귀 검증한다.
6. [x] PG·lint·source hash·한계를 기록하고 정확 SHA의 완성 draft PR을 메인에 인계한다.

## 검증 원칙

무한 재시도나 기존 기대값 완화로 실패를 숨기지 않는다. PID만으로 다른 세션을 종료하지 않으며 exact 본인 backend 식별이 없으면 서버 세션 정리 mutation을 하지 않는다. 소스가 이미 보완되었거나 재현할 수 없으면 새 제품 코드를 만들지 않고 근거를 보고한다. 각 commit 직전 현재 worktree에서 지정 `audit-staged.py`를 실행한다. 병행 서브에이전트는 읽기 전용 재현·위험 검토를 맡고 최종 2인 전문 리뷰를 대체하지 않는다.

## 실패 우선 근거

- 기존 canonical PG18 검사는 1통과(11.35초).
- 실제 runner의 lock 획득·cleanup 함수를 소유 PG18에서 실행하고 해당 backend를 SIGSTOP한 신규 회귀는 기존 script에서 1실패(6.69초): cleanup이 서버 정리 전 상태 0으로 반환했다.
- 기존 즉시 lock 부재 단언은 그대로 유지한다. 병행 읽기 전용 검토는 fence URL·전체 deadline·원래 status·타 세션 비간섭을 지적했다.

## 첫 보완 검증

- 수정 script의 신규 delay+기존 canonical 2통과(13.93초). 정상·원래37·TERM/INT143, 2차 TERM, 정지 backend timeout을 포함한 PG18 생명주기 7통과(45.63초).
- observer는 fence URL의 읽기 전용 catalog 질의만 수행하며 server4/statement5/connect2/client8+kill유예1초 상한을 둔다. nonzero는 보존하고 확인할 수 없는 정상0만3으로 바꾼다.
- 동일 key의 다른 세션 비간섭과 관측 연결 실패, 전체 관련 PG/lint 검증은 후속 확인한다.

## 대상 identity와 비간섭 보강

- 같은 advisory key의 별도 대기 세션은 본인 backend 종료 후 lock을 얻고 살아 있어야 한다. 관측 연결 실패에서도 원래37 또는 정상0→3과 고정 진단을 확인한다. 직전 전체 PG18 통합18통과(119.13초).
- 새 관측 연결에서도 기존 `write_identity_guard`를 같은 bounded psql stdin에서 재사용한다. 이 최종 source의 PG18 전체 재검증은 진행 중이며 단위12통과(0.70초)·Bash 문법·Ruff/format 통과다.
- ShellCheck는 원본과 동일한 진단7개, 신규0개다. 기존 경고를 전부 통과로 표시하거나 범위 밖 코드를 고치지 않는다.


## 최종 검증과 인계

- 조기 lock 획득 직후 종료에서는 기존 guard 정의가 아직 없다는 병행 점검을 받았다. 실제 정의 순서를 반영한 PG18 harness에서 1실패(5.25초, `command not found`)를 먼저 확인했다. guard 본문은 byte 동일하게 cleanup/trap/첫 획득 앞으로 옮기고 SQL 생성은 `write_identity_guard && cat`으로 실패를 전파한다.
- 최종 script·test source에서 PG18 전체 통합 **18통과, skip0**(121.16초), 기존 hotswap 단위 **12통과**(0.69초), Bash 문법·Ruff check/format·diff 공백 검사 통과.
- PG 통합 명령: `PYTHONPATH=$PWD/apps/api PATH=/usr/lib/postgresql/18/bin:$PATH /home/digitie/pinvi-workspaces/pinvi-codex-643/apps/api/.venv/bin/python -m pytest apps/api/tests/integration/test_restore_hotswap_preflight.py -q --tb=short`.
- 단위 명령: 같은 Linux Python·PYTHONPATH에서 `-m pytest apps/api/tests/unit/test_restore_hotswap_script.py -q --tb=short`. 의존 실행기만 원본의 기존 venv를 읽었고 app source는 본인 worktree다.
- Linux client `psql 18.6`, 서버 `postgres:18-alpine` 소유 disposable container만 사용했다. 기존 canonical 정상/실제 release SQL 실패·fencing·schema/forensic 보존 단언은 완화하지 않았다.
- 신규 9경우는 정확한 소유 backend SIGSTOP·실제 psql PID 소멸·server lock 잔류를 분리한다. 정상0/실패37/TERM·INT143, cleanup 중 2차 TERM, 영구 정지의 bounded 실패, 관측 연결 실패, 같은 key의 별도 대기 세션 생존·lock 획득을 확인한다.
- ShellCheck는 기준과 같은 **진단7개, 신규0개**이며 전체 clean 통과로 표현하지 않는다. pytest/testcontainers의 기존 deprecation 안내가 있다.
- 재현 로그는 본인 worktree의 gitignore `.codegraph/negative658-confirmed.log`, 조기 guard 결함은 `.codegraph/negative658-early-guard.log`, 최종 PG는 `.codegraph/pg658-reviewed-final.log`, 단위는 `.codegraph/unit658-reviewed-final.log`에 있다.
- 읽기 전용 병행 서브에이전트가 재현 설계와 추가 guard 결함을 점검하고 수정 script blob을 재확인했다. 이 검토는 실행 검증이나 메인의 별도 전문적 적대 리뷰 2인 승인을 대신하지 않는다.
- observer 약9초 상한은 기존 forensic 처리·psql kill/wait를 포함한 cleanup 전체 상한이 아니다. PID 재사용은 보수적 timeout을 낼 수 있다. SIGKILL처럼 EXIT trap 자체가 실행되지 않는 종료는 보장하지 않는다.
- 운영·SSH·실제 prod·Telegram에는 접근하지 않았다. 봉인 migration·frontend·다른 worker API·보호 stash를 변경하지 않았고 새 main을 통합하지 않았다.
- [Draft PR #694](https://github.com/digitie/pinvi/pull/694)를 먼저 생성·attach했다. 최종 CI는 원격 최신 SHA에서 별도로 확인해야 하며, ready/merge와 전문 리뷰 2인은 메인 담당이다.

### 검증 source 지문

문서만 후속 갱신되더라도 아래 두 source와 일치하는지 확인한다.

| 파일 | SHA-256 | Git blob |
| --- | --- | --- |
| `scripts/restore-hotswap.sh` | `609fe5f50d1032aa573822daec73a90fd85445a6732239930b770a7a7f3215fc` | `33b62499bd2036a3745576b644175024d177c2b7` |
| `apps/api/tests/integration/test_restore_hotswap_preflight.py` | `c7de59470d1cd98edc5dbd533263e21cec418b875810930e653ce38d079cb526` | `a8cac11bb6eaaa773a55086ade65652bbf1512cd` |
