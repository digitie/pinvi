# #653 상한 지정형 영구 사용자 요청 제한

## 범위

검증된 access JWT의 canonical 사용자 UUID에 한해 설정된 양의 정수 상한을 적용한다. 설정은 기본 빈 mapping이며 일반 사용자·로그인·공유 정책을 유지한다. 적용은 authenticated_default·feature_search·storage_upload_urls·trip_exports 네 정책의 독립 버킷이다. 낮은 상한도 그대로 대체하며 전역 policy 객체·identity/hash 산식은 바꾸지 않는다.

설정 대상의 유효 DB blocked는 가장 먼저 차단하고, 기존 allowed가 있어도 설정 상한을 우회하지 않는다. 대상의 blocked/allowed 공존 순서도 검증한다. 비대상의 기존 override 선택 의미를 보존한다. 관리자 bucket의 limit·차단 여부도 실제 유효 상한과 일치해야 한다.

## 순서

1. draft PR을 먼저 연다. 설정 검증·서명/만료·4정책·일반60·로그인5·상한429·override 우선순위를 실패 우선으로 검증한다.
2. 설정과 Compose 전달, 요청별 유효 limit, 관리자 관측값을 구현한다. UUID를 코드에 고정하거나 미검증 claim을 믿지 않는다.
3. 실제 PostgreSQL에서 override 조합·공유 counter/동시성·권한을 검증하고, WSL 실제 UI 발생429와 오류 안내·대조 계정·window 복구를 확인한다.
4. 변경을 자주 remote에 커밋한다. 문서·journal/resume·CHANGELOG·증거를 갱신하고 최종 전문 적대 리뷰2인·최종 SHA CI 후 일반 squash merge한다.

## 운영 경계

운영 접근·배포·테스트는 하지 않는다. 운영 UUID 구성과 기존 임시 allowed6건의 해제는 최종 담당 Claude Code가 수행할 수 있도록 절차를 문서화한다. 실제 값은 커밋하지 않는다. UUID mapping은 비밀키 회전과 무관하지만 기존 HMAC counter·DB override hash 연결은 회전하면 바뀌며 이를 숨기지 않는다. 기존 fail_open 설정의 장애 정책은 유지한다.

## 직전 완료

#673/#675는 PR679(1283736)로 완료했다. 최종860d5fb의 독립 리뷰2인 무차단·CI16상태와 WSL 관련API53·웹376·실제 UI8흐름을 확인했다. 운영 검증은 없다.
