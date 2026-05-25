# Kakao Map 통합 (폐기 — ADR-015)

> **본 문서는 폐기되었다.** TripMate v2 지도 클라이언트는 **`maplibre-vworld-js`**
> (VWorld + MapLibre GL JS, ADR-015)를 사용한다. Kakao Maps SDK는 v2에서 채택하지
> 않는다.

새 문서: **[`maplibre-vworld.md`](./maplibre-vworld.md)**.

## 폐기 사유 (ADR-015 요약)

- 좌표 순서 불일치 — Kakao SDK는 `(lat, lng)` 어댑터 필요. TripMate stack은
  `(lng, lat)` (GeoJSON / PostGIS / 라이브러리)
- 오프라인 캐싱 약관상 금지 — v2 PWA 검토 시 제약
- TripMate 도메인 마커 (Place / Price / Weather) 구현이 `maplibre-vworld-js`에
  이미 있음
- VWorld는 국토부 공식 — provider 위탁자 처리방침 간소 (국내)
- 명령형 API (`map.panTo()`) 혼용 — React 선언형 패턴과 결합 비용

## 이전 가이드

| 항목 | 이전 (Kakao) | 신규 (maplibre-vworld) |
|------|------------|----------------------|
| 환경변수 | `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` | `NEXT_PUBLIC_VWORLD_API_KEY` |
| 라이브러리 | `react-kakao-maps-sdk` | `maplibre-vworld` (github:digitie/maplibre-vworld-js) |
| 좌표 변환 어댑터 | `apps/web/lib/coordAdapter.ts` | **제거** — `(lng, lat)` 그대로 |
| CSP | `https://dapi.kakao.com` + `https://t1.daumcdn.net` | `https://api.vworld.kr` |
| 도메인 등록 | Kakao Developers 콘솔 | VWorld 개발자 센터 |
| Local 검색 | `KAKAO_REST_API_KEY` 백엔드 호출 | **`/search` endpoint 구현 변경** — 라이브러리(`python-krtour-map.search`) 경유 |
| 길찾기 (Sprint 6) | Kakao 모빌리티 API | OR-Tools 직선 거리 또는 라이브러리 추가 |

자세히는 [`maplibre-vworld.md`](./maplibre-vworld.md) §10 v1→v2 매핑.

## 폐기 일자 / ADR

- 결정 일자: 2026-05-26
- ADR-015: 지도 클라이언트 변경 (Kakao Map → maplibre-vworld-js)
- ADR-016 (이전 — frontend 스택)의 일부 정정 — react-kakao-maps-sdk 채택은 superseded
