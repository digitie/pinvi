# Common vendored artifacts

- UI: `kor-travel-ui-0.1.0-dev.9.tgz`, source `kor-travel-common@aa232ad5f255233184de80eceaab2e9b6ccb00c9`, SHA256 `b738d8824e36eb6e58d8cc6b78af7dc31233b6763248d634286044def795b403`.
  dev.9 제품 커밋은 `f0b60bb`(Common PR #47)이고, 현재 main `c289b4624c8640eb918cc915803e72ae754e58fb`의 `packages/`·루트 `package.json`/`package-lock.json`/`.nvmrc`는 aa232ad와 같다.
- Tokens: `kor-travel-tokens-0.1.0.tgz`, source `kor-travel-common@426de4fbad35282bb558712d922c06268e9aba62`, SHA256 `554ae3f6a18cbf453130b29f8a2d737ddb880101b55e14535cf8d63174b47505`. 이후 tokens 소스 변경이 없어 그대로 쓴다.
- Python: API(`[http]`)·ETL(`[dagster]`) 모두 exact `c289b4624c8640eb918cc915803e72ae754e58fb` Git dependency, 각 uv.lock 고정.
- License: GPL-3.0-or-later. Copyright 2026 Youn-sok Choi (digitie).
- Original Dagster model/UI: kor-travel-weather GPL-3.0-or-later. Tarball LICENSE/NOTICE/THIRD_PARTY_NOTICES를 보존한다.
- dev.7부터 UI는 지도 작업면(`@kor-travel/ui/map-controls`)용 runtime dependency `lucide-react` 1.41.0과 peer `@base-ui/react` ^1.8.0을 선언한다. PinVi는 `@base-ui/react` 1.9.0을 이미 쓰고 map-controls는 import하지 않는다. lucide는 루트 1.61.0과 달라 `node_modules/@kor-travel/ui/node_modules` 아래에 따로 설치된다.

## 재현과 무결성

Common `docs.yml`의 pack 절차와 같다. source checkout에서 npm 11.19.1로 `npm ci --no-audit --no-fund` 뒤
`npm pack --workspace packages/ui --pack-destination <dir>`를 실행하고, 산출물 SHA256이 위 값(Common T-217 기록값)과 같을 때만 vendor한다.
2026-10-27 N150(Node 22.22.2)에서 aa232ad의 산출물은 27파일·35441 bytes·위 SHA256으로, 대조군 `e28559803c1ec1134ef7ba7736b9acf4cadb9a32`의 dev.6은
아래 기록 SHA256으로 재현됐다. 새 버전은 **새 파일명**으로만 들여오고 `apps/web/package.json` specifier를 바꾼 뒤 npm 12.0.1의
`npm install --package-lock-only`로 lock을 갱신한다(같은 파일명의 내용만 바꾸면 lock `integrity`가 갱신되지 않는다 — `docs/agent-failure-patterns.md` 패턴 F).
lock `integrity`는 vendor 파일의 SHA-512이며 `node scripts/check-lockfile-integrity.mjs`와 `npm ci`가 확인한다.

## 이전 산출물

작업 트리에는 `package.json`이 참조하는 파일만 둔다. 아래 tarball은 PR #575(`07cfef22`)부터 dev.9 채택 직전까지의 Git 이력에 bytes 그대로 남는다.

- dev.4: SHA256 `7504b77aa451d238fdaa1a6a8f2ec43e2f0cf6ed611341a3b37a688bc9070dda`. 새 버전으로 upstream dev.3 frozen bytes를 바꾸지 않았다. 무태그 cap은 null=미확인이다.
- dev.5: source `fa8179e9c495987019494bdf28d15059f6e0aeb0`, SHA256 `bb8b0441276b208e01be55df4d03fc72dfe44226b3a7f49615bac61b48ebbbb0`. 모바일 표의 최소 너비와 내부 스크롤을 적용했다.
- dev.6: source `e28559803c1ec1134ef7ba7736b9acf4cadb9a32`, SHA256 `e4945d01d9eb89ed505a95b551899fd0ecf41be66c9ee6b76246701350447e6d`. 공통 기본 구성 너비 회귀 수정.
