# 검사 격리와 지도 회귀 묶음

## 목표

#618 mocked E2E의 미등록 요청이 운영 API로 나가지 못하게 막고, 같은 지도 검증 경로에서 #623·#686의 overlay·marker 선택·맞춤·휴게소 상세 회귀를 재현한다. 원인이 같은 코드와 helper에 걸친 항목은 한 PR에서 보완하며, 이미 수정됐거나 운영 데이터로만 확인할 수 있는 항목은 실행 근거와 함께 구분한다.

## 구현과 검증

mocked 빌드는 전용 API origin을 고정하고 공용 fixture가 미등록 API 요청을 차단·실패로 보고한다. 기존 live origin/checkout/image guard는 유지하며 live와 mocked 설정을 혼합하지 않는다. popup/context 요청·우회 경로와 의도한 로컬 소유 fixture 통신을 구분한다.

지도는 통계 칩·상단 검색/교통 패널·선택 marker·flyTo offset과 실제 적재 좌표의 맞춤을 확인한다. 휴게소 선택 실패는 test helper가 다른 feature를 고르는지 제품의 transport 선택이 잘못됐는지 분리한다. upstream marker 결함이면 소유 라이브러리부터 고치고 실제 병합본을 동기화한다. 이름·좌표를 바꿔 원래 재현을 감추거나 assertion을 약화하지 않는다. 기존 색상과 UI 컴포넌트는 유지한다.

초안 PR을 먼저 만들고 자주 원격 커밋한다. WSL 소유 API/PG/실제 브라우저의 실패 우선·회귀와 필요한 타입/lint/build를 확인한다. 두 독립 전문 적대 리뷰·정확 최종 HEAD 적용 CI 성공 후 일반 squash merge한다.

## 병행 범위

별도 worktree의 worker는 #616/#621 API 클라이언트·복원력과 #658 복원 cleanup을 진행한다. 메인과 각 worker의 코드 쓰기 경계는 분리하고 제품 묶음은 순서대로 검토·머지한다. 운영/SSH·실제 제공자/Telegram 접근은 없으며 prod 진단·적재·최종 테스트는 Claude Code 담당이다. #671/#672와 보호 stash는 건드리지 않는다.
