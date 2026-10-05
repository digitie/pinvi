# T-370: Common Dagster 복구·메모리·UI 채택

- 목적: Weather/Geo의 공통 정책을 PinVi app-owned ETL에 적용하고 2인 적대 리뷰·N150 live UI 후 PR 머지.
- base: 80c92b6c4f45a4087844efa00ee67c07e9f18142. 인간 trunk 미커밋 파일은 변경하지 않는다.
- 구현: 공통 exact dependency/배치 경계/한정 retry/nullable DTO·OpenAPI·TS/common admin 표현.
- 결정: ADR-072, 운영 전제와 실패 의미는 docs/runbooks/common-dagster.md.
- 진행: 제품 회귀·두 독립 post-fix 리뷰·N150 Chromium/Firefox live 4건 PASS. Common #27→PinVi #575 순서로 merge gate를 적용한다. 머지 이후 운영 shared policy 확인은 별도 배포 작업이다. 검증 근거는 docs/reviews/common-dagster-2026-10-05/README.md.
