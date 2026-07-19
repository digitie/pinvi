# T-ADM-C7P — PinVi API image provenance

## 목표

C7 운영 증거가 가리키는 PinVi API image ID를 실제 PinVi source commit과 결박한다. 운영자는
임의 commit을 attestation에 적을 수 없고, build context·build arg·OCI revision label 중 하나라도
다르면 build 또는 deploy 전에 실패해야 한다.

## 계약

1. `apps/api/Dockerfile`의 `PINVI_SOURCE_REVISION` 기본값은 로컬용 `development`다.
2. `staging|production` build는 40자리 소문자 Git commit만 허용한다.
   운영 node entry의 mutation 명령도 최초 resolved 환경이 명시적 `staging|production`이 아니면
   container/DB mutation 전에 거부한다. 로컬 `docker-app.sh`의 smoke 기본은 이 gate 대상이 아니다.
3. PinVi wrapper는 immutable build 전에 worktree root, clean 상태, `HEAD`와 요청 revision의
   일치를 확인한다. build context는 이후 바뀔 수 있는 live 디렉터리가 아니라 exact commit의
   `git archive`를 0700 임시 디렉터리에 펼친 값만 사용한다. ignored/untracked 파일은 들어가지 않는다.
   Dockerfile·Compose·Python 검증 helper도 같은 archive의 regular file만 허용하며 symlink와 외부
   Compose override를 거부한다. 최초 preflight에서 해석한 환경과 revision은 이후 env-file 변경보다
   우선하도록 process environment에 고정한다.
4. build·pull·migrate·up 전후에는 image의 `org.opencontainers.image.revision` label이 확정값과
   같고 `io.pinvi.build.environment` label이 deploy 환경과 같은지 확인한다.
   검증한 tag는 즉시 canonical image ID로 pin하고, 기동 뒤 container의 실제 image ID를 다시 대조한다.
   대조 실패 시 검증되지 않은 API를 Web이 노출하지 않도록 해당 Compose project의 API/Web을 제거한다.
5. 운영 1차 경로인 `kor-travel-docker-manager`도 같은 이름의 build arg를 전달하고 같은 label을
   C6c compatible-pair 증거에 사용한다. 해당 compose/service 변경은 manager 저장소가 소유한다.

## PR 범위

- Dockerfile/PinVi compose build 계약
- 공용 provenance preflight와 로컬·fallback 운영 wrapper
- 단위/정적 계약 테스트
- 배포 runbook, task/resume/journal/CHANGELOG

## 검증 순서

단일 적대적 리뷰 승인을 먼저 받은 뒤 Python unit, Ruff, shell syntax, Compose config, exact archive의
worktree drift/ignored 파일 배제, 로컬 Docker build의 development/production 양·음성 경로를 실행한다.
실제 C6c 완료 증거는 manager 연동 PR과 N150에서 image ID·revision label·clean source commit을
대조한 뒤 확정한다.

## 로컬 검증 결과

- 단일 적대적 리뷰: `ACCEPT FOR TESTS`, P0-P2 없음
- provenance focused unit: 39 passed
- API 전체 unit: 604 passed, 1 skipped
- Ruff lint/format, 신규 Python helper mypy strict, Bash syntax: 통과
- Docker Compose v5 resolved build mapping: 통과
- 실제 Docker: production + `development` revision 거부, smoke image build와 OCI label/image ID 대조 통과
- 전체 API mypy strict: 기존 22개 파일 47개 baseline 오류로 실패했으며 신규 helper에는 오류가 없다.
- 남은 gate: 최신 main rebase/CI, manager 연동, N150 prod image provenance와 live UI E2E
