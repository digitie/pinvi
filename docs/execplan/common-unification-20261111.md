# 관리자 공통 UI 이관 실행 계획

사용자 승인 범위는 Pinvi 관리자 웹과 모바일의 common 의존성·표·Radix UI·지도 산출물 및 검증이다. Concierge는 별도 전담에게 인계했다.

1. 필수 문서·table/overlay/map 조사와 부모 계약 공유.
2. common VirtualTable 및 Radix 프리미티브 이관, 폼·Zustand·Pretendard 실제 소비.
3. 동일 vendor 산출물·lock 갱신과 CI guard 연결.
4. Linux lint/typecheck/unit/build 및 N150 브라우저 검증.
5. 한국어 기록·명시적 git add·commit. push/PR은 부모 통합 후.

진행 상황과 한계는 [조사·이관 보고서](../reports/common-unification-20261111.md)에 기록한다.

현재 구현은 검토용 checkpoint이며 배포용 완료가 아니다. 마지막 공통 c6·GPL 포함 vworld core/RN1.0.1·web1.0.3 및 Lightning CSS1.33 원본 fix 수신 후 lock/원장/전체 gate를 한 번 더 맞춘다. 두 독립 적대 리뷰와 CI·merge·부모 go 이후에만 이미지 배포한다.
