# 관리자 Feature 목록·상세 전용 읽기 자격

## 최종 공개 R7과 원 일정 복원

최종 공개 TLS 읽기 R7은 Map7·PinVi6, 총13단계를 통과했다. 운영의 실제 기존 행 목록·선택·
동일 ID 상세/성공 DOM·인증 reload·지도와 lineage를 확인했으며 synthetic 취소/create/approve 등
업무 쓰기는 실행하지 않았다. 성공 실행에서 양쪽 로그인·로그아웃 POST는 각각1회다.
Map은 로그인200·인증 읽기200·logout200·보호401, PinVi는 로그인200·logout204·보호401을
확인했다. PinVi의 실제 지도 tile21개·오류0, 목록 GET2004회·단건 GET2002회다.

Map 하네스는 routing의 native cache 비활성화와 구분하여 같은 origin의 허용된 불변 정적 파일만
첫 실제 public 응답의 status/header/body를 RAM에 보관해 재사용했다. 인증/API/HTML/provider는
이 캐시의 대상이 아니다. 첫 응답의 유효 freshness175초 이상·항목4MiB/합16MiB·192개/동시4를
검증하고 실제 네트워크 상한256은 유지했다. 실제 허용204·cache miss71/hit80·retained peak
3,682,149B·동시4를 관측했다. hit80은 실제 HTTP80회나 새 서버 응답 검증으로 세지 않으며,
이 bytes 지표를 전체 브라우저/Node RSS 상한으로 쓰지 않는다. 원blocked0/13단계/reload를
유지했고 최종 차단·page/hydration/cache/late 오류0·route 정산 완료다.

이번 실행의 원 env·7개 runtime identity와 브라우저 inventory106개는 전후 같았고 소유 process와
profile을 제거했다. 새 두 테스트 세션의 미철회 가능성False는 이번 성공 실행의 결과이며,
아래 원3 FAIL과 R4의 possible_unrevoked=True를 고치지 않는다. Map 인증은 stateless cookie
경계이고 폐기된 원 R4 cookie를 복원하거나 계정 전체 철회·키 회전을 하지 않았다.

원 Map instigator는47개/RUNNING38개였고 최종51개/RUNNING37·STOPPED14를 확인했다.
새 항목은 모두OFF이며 퇴역한 feature_notice_transport_highway_incidents_ten_minute_schedule은
복원하지 않았다. 전체 수집·신규 schedule 활성화나 W/T opt-in 완료를 뜻하지 않는다.
전용 읽기 자격은 Map API digest만·PinVi API raw만 유지하며 PinViWeatherOFF도 유지했다.

이 정산은 배포된 현재 pair의 읽기/auth와 원 일정 복원에 한정된다. Rest431/432 영속 연결,
물리 두writer·전체 수집 CPU/메모리 개선·상위 전체1commit은 별도 미완이다.
공개 원본 SHA-256 c2f8b77347606329485730d650e52ef227731b920bf4e5022466f98ef93523d7,
독립 수용 b8c77588de604d95b522092756c71b131ae6905ef01afe4d277ff59c932cc6e7,
일정 복원 수용 168bf634847cffc56013c4e6aea5921129642b7b0b7ba621dbf0e70a19866735.

## 2026-10-26 현재 상태 — 머지·격리 후보·최종 배포 완료, 공개 읽기·일정 복원 수용

PR #602의 최종830260bd는8f1b998f로 머지됐으며 두 Git tree가 같다. Map #1414/#1411은
최종5f3506a에 포함됐다. 아래 구현·검증 세대의 미완 표기는 당시 기록으로 유지한다.
기존 코드 CI10 성공·독립 제품 검토와 새 pair의 실제 결과를 합산하지 않는다.

최종 격리 pair는 Map860967df/PinVi830260bd를 실행했다. Map 후보와 최종 머지의 제품·
스키마·UI 입력 동등성은 테스트·문서 변경과 분리해 확인했다. PinVi는 비인증401,
로그인·두 HttpOnly cookie·reload, 실제 VWorld canvas/tile, 목록 검색·category·admin DTO,
같은 source의 상세 lineage, 로그아웃204·보호401의6단계를 통과했다. 성공 실행의 로그인·
로그아웃 POST는 각각1회, 실제 Map 목록 GET200은2회·단건 GET200은1회, 지도 tile16개다.
테스트 세션1개가 철회됐고 임시 DB·role·브라우저 profile·프로세스·정확 PG 자원을 정리했다.
이 후보는 격리 HTTP이며 실제 공개 TLS·운영 데이터·최종 배포 성공을 뜻하지 않는다.

앞선3 FAIL은 관리 migration fence 준비 누락, Node 진입점 미호출, 로그인·reload 단계
실패로 보존한다. 세 번째는401만 통과했고 상세 상태가 없어 실제422를 관측했다고 쓰지
않는다. 초기17/174, 빈 env P2, 포맷·provenance CI 실패도 아래 원 기록대로 남긴다.
후속 성공을 원 실패의 성공 재해석이나 단일 통과 합계로 사용하지 않는다.

새 Map·PinVi 백업의 공식 격리 복원 리허설은 모두 verified로 통과했다. Map은 scratch의
소유권·ACL·routine 보안 속성에 대한 비차단 REHEARSAL_CATALOG_DRIFT 경고를 보존하며 catalog
전체 일치를 주장하지 않는다. 운영 첫 Map418+기존 PinVi commit 뒤 정본 Manager의1키 명시 provision·최종
Map5f3506a/PinVi8f1b998f rotate·공식 rebuild가 완료됐다. committed·경고0 영수증과
Map schema430·PinVi schema0102·7 healthy·runtime identity 일치를 새 readback했다.
읽기 자격은 Map API digest만·PinVi API raw만 전달됐고 같은 CAS 원천 일치와 WeatherOFF를 확인했다.

첫 공개13flow 실행은 Map 비인증401 뒤 로그인 POST401로 실패해 PinVi에 도달하지 못했다.
finally logout 요청1회와 소유 브라우저/profile 제거·원 env 불변·미철회 테스트 세션 없음은
확인했다. 원 실패를 보존하며 이 첫 시점에는 공개 PinVi6단계 인수·원 일정 복원·운영 종결이 미완이었다.
이 문서 변경은 자격·설정·DB·컨테이너를 변경하지 않는다.
최종 배포 수용 readback SHA-256은
e0b0a119123c4211c4e7f33809d9e9d3dfa31e86ff8d44c1db754297e51089cf,
첫 공개 실패 영수증은
efe30f095d98783451d0b52a8da169a96f58f65ddf558db59d1c6ed6be2926ec다.

두 번째 공개 실행도 별도 실패로 보존한다. Map 비인증401·로그인200/보안 HttpOnly cookie·
hydration·지도/목록 기본 표시의 첫4단계 뒤 기존 행 상세 단계에서 TimeoutError가 발생했다.
차단 요청25개·provider tile40개가 관측됐지만 상세 성공이나 PinVi 단계 통과로 세지 않는다.
로그아웃 POST0으로 테스트 세션 철회는 미확정이다. 소유 브라우저/profile 제거와 원 env 불변만
확인했으며 원인 분리는 별도 후속으로 진행했다. 이 실행의 미확정은 그대로 남긴다. 원 실패 SHA-256은
1886316e23b2e6b5c904ce049aaa3fc1e449fb4cc786842431333f04ab79aaac다.

세 번째 공개 실행은 Map 실상세까지5단계를 통과한 뒤 명시 reload의 요청 예산 소진으로 실패했다.
허용256/시도281·예산 차단25개이며 다른 범위 차단0이었다. logout1·보호401·이번 실행의
미철회 가능성False와 정확 정리를 확인했지만 PinVi는 미도달이다. 원 두 실패·두 번째 실행의
미확정 표기는 그대로 보존한다. 이 세 번째 실패를 공개13flow 완료로 세지 않는다.
세 번째 원 실패 SHA-256은
2ecff5b22193e3d0bdb360e5e067692e76c890f0e5af1f789b592aba767fd244다.



선별 증거 SHA-256: 격리 pair 수용
`a75474bd6185d8e83062e5b7768af198eb48f4b2286f55a129c5ffae9e61cb65`,
독립 검산
`0300cfd1c56b0811fee2e88a8b973b3c027da43b7fd2b025cb73eb00940e0d2b`,
첫418 commit·runtime readback
`63f51b27f44da72ce3301746d3676a7676efb36831f8faa03b1c892510d51ee9`.


운영에서 관리자 Feature 목록의 Map 403이 PinVi 422로 표시됐다. 기존 일반 service
credential은 관리자 BFF 권한이 없었다. 기존 서비스 토큰 헤더를 사용하는 전용 읽기
자격으로 목록·상세만 호출하며 기존 admin 쓰기·revision·ops 권한은 유지한다.

- 경로: GET /v1/service/admin-features, GET /v1/service/admin-features/{feature_id}.
- PinVi 설정: PINVI_KOR_TRAVEL_MAP_ADMIN_FEATURES_READ_TOKEN(선택 SecretStr).
- Map 설정: KOR_TRAVEL_MAP_API_PINVI_ADMIN_FEATURES_READ_TOKEN_SHA256.
- Map 권한: pinvi:admin-features:read. 기존 admin DTO·필터·페이지네이션을 공유한다.

설정하면 32자 이상·Unicode whitespace 없음·다른 Map 자격과 별개인 값을 요구한다.
미설정 또는 빈 env는 None으로 정규화하여 앱 기동을 보존하고, 해당 두 조회만 HTTP 전에
503으로 차단한다. 다른 자격으로 fallback하지 않는다. Map의 401·403도 해당 두 조회에서만
안전한 503으로 분류하고 재시도하거나 원 오류 본문을 노출하지 않는다. 실제 query 422는
기존 입력 오류로 유지한다. with_request_id와 factory가 별도 자격을 보존하며, 새 token은
브라우저·공용 응답·admin write·revision·ops 요청에 보내지 않는다.

Map digest 제거·교체로 읽기 권한을 회수하며 별도 만료 시계는 없다. PinVi 자신의
admin/operator 권한 검증과 사용자 인증은 유지한다. 실제 provision은 Manager 정본으로
최종 Map/PinVi pair 전환 직전에만 수행한다.

## 검증 세대와 원 실패

초기 d3c5에서는 신규17개와 기존 회귀를 합쳐174 PASS였다. 이 검증은 mock HTTP이며,
빈 env를 잘못 거부하는 기대값도 포함해 앱 기동 호환성을 입증하지 못했다. 독립 리뷰가
이 P2를 확인했고, 7aa0은 기존 선택 secret 정규화에 필드 한 개만 추가했다. None/빈 env의
factory 요청 차단과 기존 비어 있지 않은 짧은 값·whitespace 거부를 유지한 신규18개가
통과했다. 원17/174 결과와 P2 HOLD는 이력으로 보존하며 현재 검증 수로 대체하지 않는다.

6715에서는 Map8555의 admin/service 스펙을 exact bytes로 재vendor하고 single pin·literal
계약을 갱신했다. M05는 정본 생성기로 계산했으며 service provenance는 원 capability/
version을 유지하고 실제 artifact hash/revision을 반영했다. user 스펙은 불변이다.
새 두 GET의 동일 DTO·query/path parameter·ServiceToken·GET-only 계약을 포함해 관련
121 PASS/3.96초를 확인했다. PinVi 제품은 W/T 독립 FULL 승계와 빈 env P2 closure를
완료했고, vendor T 검토를 받았다. 최종 문서·CI 정산 검토는 별도다.

같은 고정6715의 로컬 Python3.13.14에서 API unit 전체는 1809 PASS/9 SKIP/5 warnings, 109.36초다.
9 SKIP은 기본 위치의 Map checkout 비교1건과 Manager checkout 연동8건 부재이며,
통과한 것으로 세지 않는다. 새 vendor는 별도로 고정 Map Git blob과 전수 바이트 대조했다.
기존 API OpenAPI 검사도 전체 unit에 포함되며 PinVi route/DTO와 TypeScript DTO 소스는
부모와 같다. 이 결과는 실제 PG·운영 호출·새 pair UI 증거가 아니다.

6715 CI의 API integration 4개 shard와 web 검사들은 성공했다. API lint/unit job은
4개 파일의 Ruff format에서, Docker provenance job은 재vendor 전 원 artifact hash
literal에서 실패했다. 원 로그를 보존하고 CI와 같은 cached Ruff0.17.2로 해당4개만
정렬했으며 Python AST 전체 동일성을 확인했다. workflow의 wheel/service와 Docker
provenance exact hash 두 literal만 실제 파일에서 계산한 값으로 맞춘다. 원 단언과
검증 경계를 유지하며 새 CI 성공으로 재해석하지 않는다. 수정 뒤 같은 CI Ruff0.17.2의
전체 API check/format471개, 전체 mypy254개와 집중34 PASS/5.77초를 확인했다.
CI의 Python3.12·실제 image 검증은 후속 run으로 확인한다.

## 남은 수용

Map8555는 수동 생성 token과의 digest 중복 P2를 발견해 HOLD 상태이며 최소 수정과
독립 두 리뷰가 필요하다. Manager557은 별도 source 검토/CI 수용 대상이다.
새 PinVi 최종 CI·compatible pair/UI·명시 provision·머지·배포는 미완이다.
이 단계에서 credential·DB·운영 설정은 변경하지 않았다.


## 코드 checkpoint의 CI 수용

bbf3의 정확 head를 API와 Web checkout 모두 확인했고, CI10개가 SUCCESS다.
API lint/type/unit·integration4 shard·Docker provenance·contract pin의7개와
Web type/build·Docker·E2E의3개다. Aggregate CI·review reminder·staleness SKIP3개는
성공 개수에 포함하지 않는다. CI Python3.12.15 unit은1809 PASS/9 SKIP/6 warnings,
111.78초이며 실제 wheel·Docker의 packaged provenance 검사도 통과했다.

bbf3 formatter/두 hash/문서 delta는 Root/T 독립 검토를 완료했다. 이 절의 후속
문서 전용 checkpoint는 제품·계약·workflow를 바꾸지 않으며, 위10개는 bbf3 코드의
증거다. 새 head의 별도 검사와 혼동하지 않는다. 원6715 CI 실패는 보존한다.

Map read/create P2는488d의 Root/T 독립 source 검토에서 닫혔다. 원8555 HOLD는
이력으로 유지하며, 이후 Map 동결 baseline/pending receipt의 metadata 정렬과
새 정확 CI는 별도다. Manager557도 별도 source/CI 수용 대상이다.
CI Web E2E는 새 운영 pair의 공개 UI 검증을 대신하지 않는다. 실제 pair/UI·명시
provision·머지·배포는 여전히 미완이며 이번 작업의 운영 변경은 없다.
