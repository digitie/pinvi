# T-VN-41-P — n150 격리 paired live 증명

## 목적

이미 병합된 Map producer와 PinVi generation 7 consumer가 실제 격리 스택에서
`command → state_applied → inbox → ACK → cache generation → tombstone` 인과 사슬을
끝까지 보존하는지 확인한다. 이 문서는 `T-VN-41-P`의 마지막 n150 증명 단위를
PR 단위로 분리한 실행 정본이다.

## 범위와 경계

- n150의 **격리** Map DB·PinVi DB·Compose project만 만든다. 운영 Compose, 운영 DB,
  사용자 여행/POI, docker-manager의 운영 manifest와 PR #119는 읽기·수정 대상이 아니다.
- 실행 시점의 PinVi `origin/main`, Map `origin/main` commit과 이미지 ID를 증적에 남긴다.
  Map image는 PinVi generation 7 functional owner가 ancestry로 포함되고 vendored service
  OpenAPI SHA-256가 같은 경우에만 허용한다.
- ordinary command/consumer token만 격리 API container에 주입한다. restore-fence/recovery
  credential, Admin credential, 원문 token·URL·host는 어떤 stdout, journal, PR에도 남기지 않는다.
- final production consumer enable과 `pinvi-cache-target-final-boundary finalize`는 Lane A
  `T-VN-H42`와 docker-manager 재pin이 끝난 뒤의 별도 작업이다. 이 PR은 그 경계를 열지 않는다.

## 실행 순서

1. n150에서 격리 checkout을 두 repository의 현재 `origin/main`으로 동기화하고, Map service
   OpenAPI bytes/SHA-256, PinVi generation 7 runtime pin, Map functional-owner ancestry를
   오프라인으로 확인한다.
2. 고유 Compose project·고유 volume/DB 이름으로 Map과 PinVi의 격리 stack을 기동한다. sync는
   최초에는 off로 두고 migration·health·default-off readiness를 확인한다.
3. command/consumer token을 교차한 negative probe가 source mutation과 consumer read/claim을
   모두 `403`으로 거부하고 원격 상태를 바꾸지 않는지 확인한다.
4. 정상 역할 token으로 initial cutover/backfill과 snapshot Merkle/count/high-watermark 수렴을
   확인한 뒤 sync를 격리 stack에서만 활성화한다.
5. UUID가 새로 발급된 `pinvi-cache-target-causal-canary --timeout-seconds 180`을 실행한다.
   PUT·event·ACK·cache generation·DELETE, pending/leased/dead=0, local applied/ACK/remote snapshot
   cursor의 exact equality, count/Merkle equality를 receipt로 확인한다.
6. 같은 event page 재전달(duplicate), consumer pause 중 source write 뒤 resume(recovery), restore
   epoch 전환 뒤 old cursor 거부를 각각 실행한다. inbox side effect는 한 번만, 회복 뒤 lag/DLQ는 0,
   snapshot count/Merkle는 exact equality여야 한다.
7. Map cache-target recovery admin UI와 PinVi live UI의 해당 격리 spec을 n150 Playwright Docker
   runner로 실행한다. runner가 Ubuntu browser 지원 문제로 시작하지 못할 때만 원인을 기록하고
   Windows fallback을 쓴다.
8. 성공 receipt·redacted command/event/claim/ACK ID·epoch·cursor·snapshot ID/count/root·두 image ID와
   실행 시간을 PR 기록에 남긴다. 격리 stack/volume은 결과가 저장된 뒤 제거한다.

## 중단 조건

다음 중 하나면 consumer를 계속 켜 두지 않고 격리 stack을 정리한 뒤 task를 보류한다.

- service OpenAPI SHA-256, generation, functional-owner ancestry 중 하나라도 불일치한다.
- role 교차 probe가 허용되거나 원격 상태를 바꾼다.
- canary가 terminal 실패, cursor/count/Merkle 불일치, pending/leased/dead backlog를 남긴다.
- duplicate가 inbox side effect 또는 cache generation을 추가로 증가시키거나 old epoch/cursor가 적용된다.
- 테스트가 격리 project 밖의 컨테이너·DB·volume을 대상으로 한다는 징후가 있다.

`429/503` 재시도와 network timeout은 같은 run ID를 이용한 resumable 경로만 허용한다. `401/403`,
`413`, 계약·checksum 오류는 terminal fail-close로 기록하고 자동 재시도하지 않는다.

## 완료 조건

- 위 1~7의 n150 실행이 모두 통과하고, 증적은 비밀·운영 주소 없이 journal/resume/PR에 남는다.
- `docs/tasks.md`의 n150 paired live proof 체크를 완료로 바꾸고 `T-VN-41-P`를
  `docs/tasks-done.md`로 이관한다.
- 이 결과만으로 production consumer enable을 완료 처리하지 않는다. Lane A 경계와 final boundary는
  열린 상태로 유지한다.
