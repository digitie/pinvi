# Expo SDK57 패치 정합성

## 목표와 범위

PR693의 참고 Expo doctor가 보고한 SDK57 패치 불일치를 모바일 manifest와 루트 lockfile에서 함께 보완한다. SDK major·React/RN·기존 install.exclude·CI 필수 여부·애플리케이션 동작은 변경하지 않는다. 공식 Expo 권장 버전과 현재 설치를 먼저 대조하며 진단을 통과시키려고 제외 항목을 추가하지 않는다.

## 절차

초안 PR을 먼저 게시하고 중간 결과를 원격에 저장한다. WSL에서 doctor 실패를 재현한 뒤 SDK 권장 패치를 고정하고 clean npm ci·doctor·모바일 lint/typecheck·Metro export 및 공유 workspace 검사를 실행한다. 실기기·EAS·운영 배포는 수행하지 않으며 검증 한계를 기록한다.

최종 커밋은 두 독립 전문 적대 리뷰와 정확 HEAD의 적용 CI 성공 뒤 일반 squash 병합한다. Map1440 소스 누락 여부와 Map1450 갱신 구조는 서브에이전트가 읽기 전용으로 병행 확인한다. Map1450 갱신 정책의 기존 질문은 선택 대기다.

## 검증 결과

초기 doctor는 SDK 권장 패치6개 불일치로20/21 실패했다. mobile만 올렸을 때 root Expo57.0.31과 native module 중복도 재현해 root/mobile을 함께57.0.32로 맞췄다. 전체 dedupe는 채택하지 않았고 npm12 full install 결과에서 관련 없는 optional font·type·gesture-handler의 기존 완전한 lock 엔트리를 보존했다. 최종 Node22.23.1/npm12.0.1 clean ci, doctor21/21, lock1226/1226 integrity, workspace lint/typecheck·unit608, Android/iOS Hermes와 web35route static export, production Next+Chromium UI202통과/기존3skip을 확인했다. router-server의 실제 _ctx-shared 해석에 symlink를 추가하지 않았다.

세부 입력·로그 hash와 실기기/EAS/운영 미검증 범위는 docs/reviews/expo-57-patch-alignment.json에 기록했다. 필수 CI·Docker 소비 검증은 최종 HEAD에서 확인하며, 최종 SHA와 독립 리뷰 결과는 PR696에 남긴다.
