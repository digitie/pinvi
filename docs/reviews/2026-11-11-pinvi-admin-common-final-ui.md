# PinVi Admin 공통 셸 최종 테스트 수정 독립 UI 리뷰

- 실행 ID: pinvi-ui-final-20261111T043207Z
- 검토 시각: 2026-11-11T04:32:07Z ~ 04:32:09Z
- 저장소: /home/digitie/pinvi-codex (WSL Ubuntu-26.04)
- 이전 후보: 74f894baec561c78474348f450d6ccdb1f9467d0
- 최종 immutable candidate: 8ee56763b66f261f18e1c2ebcfbed4cf605bbf7f
- tree: d274634a770c9ebe34480e33e30b8751f5e69cdc
- 시작·종료 HEAD 모두 최종 후보와 동일, status 모두 clean.
- git object-only 전체 delta를 확인했다. 상대 최신 리뷰를 읽거나 소스를 수정하지 않았다.

## 변경과 판정

변경은 apps/web/e2e/admin-common-shell.e2e.ts 한 파일,3줄 삽입·1줄 삭제다. 전역 getByRole(alert)를 admin-sidebar 내부 getByRole(alert)로 좁혔다. 실패 로그아웃 alert는 실제 제품 마크업에서 sidebar 내부에 있으므로 assertion이 해당 오류를 계속 검증한다. Next route announcer 등 sidebar 외부 alert와의 strict-mode 충돌을 피하면서 오류 문구·실패 후 현 URL 유지·재시도 후 로그인 이동 assertion을 유지한다. 제품 코드 변경은 없다.

- PASS: immutable tree·시작/종료 HEAD/status·전체 delta 정적 검토·git diff --check.
- 새 finding 없음. 기존 UI-01 코드 수정에 영향 없음.
- 코드 리뷰 판정: PASS.
- NOT_RUN(본 리뷰어 직접 실행 없음): 최종 후보의 Linux 검사 및 N15003 실행.
- 실행 gate: OPEN. 최종 N15003 결과는 작성자가 진행 중이므로 브라우저 PASS나 작업 전체 완료를 선언하지 않는다.
