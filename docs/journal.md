## 2026-10-24 — 여섯 프로젝트 npm 보안·버전 정합

- 직접/전이 npm 의존성과 잠금 파일을 갱신하고 여섯 프로젝트의 공통 버전을 맞췄다.
- 호환성 예외·미수정 상류 권고·검증 범위는 [정합 기록](npm-security-alignment-2026-10-24.md)을 따른다.
- 현재 WSL 회귀와 CI·독립 리뷰·N150 후보 UI 검증 진행 중이며, 통과 확인 전 머지하지 않는다.

## 2026-10-24 (claude) — `shell-quote` critical 권고 해소: 루트 override (브랜치 `fix/shell-quote-override`)

`apps/mobile`의 `react-native@0.86.3` → `react-devtools-core@6.1.5` → `shell-quote@1.10.0`이 GHSA-pqg4-j6r4-53mv(critical,
`>=1.8.4 <1.11.0`, 수정 1.11.0) 범위였다. `react-devtools-core`가 `^1.6.1`을 요구하므로 상위 bump 없이 루트 `overrides`에
`"shell-quote": "^1.11.0"`을 더했다(기존 `postcss`·`sharp` override와 같은 방식).

- lockfile은 Node 22 + npm 11.19.1(CI 동일)로 node_modules 없이 `npm install --package-lock-only` 재생성. diff는
  `node_modules/shell-quote` 한 항목(1.10.0 → 1.12.0)뿐이고 integrity 게이트 100%.
- `npm audit --omit=dev`: 21건(critical 2 = `next`·`shell-quote`) → 20건(critical 1 = `next`, #596이 처리).
