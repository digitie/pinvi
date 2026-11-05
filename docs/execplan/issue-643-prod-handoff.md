# Pinvi 운영 검증 인계와 남은 두 이슈

## 목표

Claude Code가 운영 검증을 이어갈 수 있도록 #643 관련 머지 내역과 #650 주소 검색·Map #1450 국립공원 경계 적재의 진단 순서, 실행 기준, 완료 조건을 저장소 런북에 모은다. 사용자가 2026-11-06 다시 확인한 범위는 Codex의 WSL 작업·검증·머지이며 prod는 Claude Code 담당이다.

## 범위

#650의 원래 주소와 운영 재현, Geo623 공식 원천 WSL 검증을 구별한다. 운영 worker·image·입력·DB/search_path·원천·서빙 MV를 대조하기 전 원인을 확정하지 않는다. SRCH-004의 구형 이슈 종료 기록을 현재 재오픈 상태로 정정하되 실제 테스트 단언은 유지한다.

Map #1450은 국립공원 경계 dataset인 knps_park_boundaries와 특별보호구역 knps_protected_areas를 구별한다. 기존 job/config·운영 검증 경로를 소스와 대조하고 실제 원천·적재·서빙·Pinvi SRCH-028의 완료 조건을 명시한다. 운영 적재 완료를 WSL fixture 성공으로 대신하지 않는다.

두 전문 서브에이전트가 각각 Map과 Pinvi/Geo를 병행 조사하며 열린 이슈·열린 PR·이미 머지된 작업·운영 전용 잔여를 구별한다. 다른 Code의 #671/#672와 보호 stash는 건드리지 않는다.

## 진행 순서

초안 PR을 먼저 만들고 기록을 자주 원격에 남긴다. 관련 문서와 카탈로그를 한 PR로 묶고 관련 정합성 검증을 WSL에서 수행한다. 두 독립 전문 적대 리뷰를 거쳐 최종 정확 HEAD의 적용 CI 성공 후 일반 squash merge한다. 운영 접속·배포·적재·검증과 Telegram 전송은 이 PR에서 실행하지 않는다. 두 제품 이슈는 운영 완료 조건이 확인될 때까지 열린 상태를 유지한다.

## 영역 검사 러너의 설정 전달 결함

운영 카탈로그는 PINVI_E2E_GEOMETRY_AREA_ANCHOR_QUERY와 설악산/북한산 anchor를 읽지만 n150-playwright-runner.sh의 Docker 환경 전달 목록에는 세 키가 없었다. 실제 Bash allowlist/argv 구성 조각을 격리 실행해 세 누락을 수정 전3실패로 확인했다. 허용 목록에 세 이름만 추가하며 값은 argv에 넣지 않는다. 설정하지 않은 키와 알 수 없는 키는 계속 전달하지 않는다.

N150 host·exact revision·clean checkout·고정 이미지·새 npm ci guard는 그대로다. WSL 검증은 실제 Bash argv 경계이며 N150/Docker·prod UI 실행을 대신하지 않는다. 보완 후 신규4·이미지 계약2·기존M05 wiring20 합계26검사, Bash 문법·Ruff/format이 통과했다. 제품 코드/UI가 아닌 운영 검사 러너의 전달 경계를 보완한 것으로 PR 범위를 갱신한다.
