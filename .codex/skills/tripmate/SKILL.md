---
name: tripmate
description: TripMate 여행 계획 web app에서 작업할 때 사용한다. 일정, 목적지, 예산, 지도, 협업 기능의 제품 어휘, UX 기본값, 구현 guardrail을 제공한다.
---

# TripMate Skill

## 문서 언어 정책

TripMate의 모든 Markdown/RST 문서는 한글로 작성한다. 코드 식별자, 명령어, URL, provider 원문, API field처럼 그대로 보존해야 하는 값만 영어를 유지한다.

## 제품 형태

TripMate는 여행자가 아이디어를 실제 일정으로 바꾸도록 돕는다.

- 목적지와 저장 장소를 모은다.
- 날짜, 비용, 이동 시간, 취향을 비교한다.
- 일자별 여행 일정을 만든다.
- 동행자와 의사결정을 조율한다.
- 예약 상태, 메모, 이동/운영 정보를 추적한다.

## 핵심 객체

- `Trip`: 목적지, 날짜 범위, 동행자, 예산, 계획 상태
- `ItineraryDay`: 여행 안의 하루
- `Place`: 관광지, 식당, 카페, 숙소, 역, 공항, 사용자 지정 stop
- `RouteLeg`: 장소 사이 이동, 소요 시간, 이동 수단, 비용
- `BudgetItem`: 예상 또는 확정 비용
- `CompanionPreference`: 투표, 제약, 꼭 가야 할 항목, 식이/접근성 요구

## UX 기본값

- 현재 여행, 일정, 저장 장소, 계획 결정처럼 실제 작업 표면에서 시작한다.
- 날짜, 위치, 비용, 이동 시간을 action 가까이에 둔다.
- 계획 밀도를 위해 compact list와 timeline을 사용한다.
- 위치 관계가 중요할 때 map을 쓰되, map 없이도 일정 편집이 가능해야 한다.
- `idea`, `shortlisted`, `booked`, `skipped`처럼 불확실한 계획 상태를 지원한다.
- 투표, comment, preference summary로 협업 상태를 드러낸다.

## Copy style

- 짧고 구체적이며 여행 맥락에 맞게 쓴다.
- “장소 추가”, “날짜 비교”, “숙소 예약”, “일정 공유”, “비용 나누기” 같은 action 중심 문구를 선호한다.
- “생산성 향상”, “workflow 혁신” 같은 일반 SaaS 표현은 피한다.

## Engineering guardrail

- 날짜나 schedule logic을 추가할 때 timezone을 명시적으로 model화한다.
- 모든 여행이 해외, 1인, leisure, flight-based라고 가정하지 않는다.
- 비용은 currency-aware하게 유지한다.
- 접근성 요구와 식이 제약은 edge case가 아니라 일반 planning data로 취급한다.
- Map, place, flight, hotel, weather, AI 외부 API를 통합할 때 provider, env var, rate limit, fallback을 문서화한다.

## Verification checklist

- Mobile layout에서 itinerary editing 중 horizontal overflow가 없다.
- Empty state는 명확한 다음 action 하나를 제안한다.
- Saved/demo data는 sample data임이 보인다.
- 날짜, 통화, 거리 format이 일관된다.
