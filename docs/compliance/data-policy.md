# 외부 Provider 데이터 정책

Kakao / Naver / Google / VWorld / Juso 등 외부 provider TOS 준수 정책.
v1 `docs/data-sources.md` + `skills/data-policy.ko.md` 정리.

> **scope 주의**: 한국 공공 API 데이터(KMA/KHOA/OpiNet/KREX/KRMOIS 등) ETL 적재
> 정책은 **`python-krtour-map`이 소유** (ADR-003 / ADR-005). 본 문서는 TripMate가
> 직접 호출하는 provider (소셜 OAuth / 지도 SDK / Local API / Gemini / Resend /
> Telegram)에 한정.

## 1. 일반 원칙

- provider TOS 준수 (회의 시점 확인)
- raw 응답 long-term 저장 X (필요 시 라이브러리 측 source_records에만)
- 다른 지도/검색 결합 표시 금지 사항 준수
- 같은 region + time window 데이터가 있으면 외부 API 반복 호출 X
- 키는 환경변수 + 마스킹, raw 로그 X
- 사용자 가시 결과는 provider 라벨 명시

## 2. Provider별 정책

### 2.1 Kakao Map SDK + Kakao Local API

- **오프라인 캐싱 약관상 금지** (지도 타일)
- 서비스 워커 `NetworkOnly` 강제 (PWA v2 후보)
- 일 호출 한도 Kakao 콘솔에서 확인 후 클라이언트 viewport 디바운스 + cache
  (`docs/integrations/kakao-map.md` §3)
- 도메인 화이트리스트 (콘솔)
- `KAKAO_REST_API_KEY` server-only, `NEXT_PUBLIC_KAKAO_MAP_APP_KEY` 브라우저 (origin
  화이트리스트로 보호)
- 로그에 raw 응답 / full query / 키 미포함

### 2.2 Naver / Google / Kakao OAuth

- access / refresh / id token **장기 저장 X**
- profile fetch 즉시 폐기
- 이메일 자동 연결 X — provider_user_id (`sub` / `response.id` / `id`)만 식별자
- Google `email_verified=true` / Kakao `is_email_valid && is_email_verified` 필수
- Naver는 별도 verify 발송
- 자세히는 `docs/integrations/social-login.md`

### 2.3 Google Gemini API

- 사용자 개인 API 키 (시스템 키 별도)
- 키 원본 DB/로그 저장 X — `secret_ref` + `masked_fingerprint`
- YouTube URL passthrough만 (다운로드 X)
- private/unlisted 영상 skip
- 결과는 별도 테이블 + "Gemini 생성" 라벨 + 출처 인용
- 자세히는 `docs/integrations/gemini.md`

### 2.4 Resend 이메일

- 도메인 인증 (SPF/DKIM/DMARC) 없이 발송 금지
- bounce / complaint → 발송 차단 + audit
- 마케팅 발송은 별도 동의 (`marketing` consent)
- 자세히는 `docs/integrations/resend.md`

### 2.5 Telegram Bot

- bot token 원본 DB 저장 X — `telegram_bot_token_ref` (env name 또는 vault ref)
- target 등록 시 `getChat` 또는 `sendMessage` 검증
- 일반 user 알림에 stack trace / dataset key / 키 포함 X
- 자세히는 `docs/integrations/telegram.md`

### 2.6 Sentry SaaS

- `before_send` PII 마스킹 (이메일 / 좌표 / 토큰 정규식)
- DSN 노출 가능 (security X)
- 처리방침에 위탁자 명시 (미국)
- 자세히는 `docs/integrations/sentry.md`

## 3. 라이브러리 위임 provider (`python-krtour-map` 소유)

다음 provider는 본 저장소가 직접 호출하지 않음 — `python-krtour-map.providers`가
호출 + raw 적재:

- 기상청 (`python-kma-api`): 단기 / 중기 / 실황 / 특보
- 한국관광공사 (`python-visitkorea-api`): 축제 / 관광지 / 국가유산 후보
- 한국석유공사 (`python-opinet-api`): 유가
- 한국도로공사 (`python-krex-api`): 휴게소 / 휴게소 날씨
- 환경공단 (`python-airkorea-api`): 대기질
- 행정안전부 (`python-krmois-api`): 인허가 LOCALDATA
- 국립해양조사원 (`python-khoa-api`): 해양 지수 / 해수욕장
- 국립공원공단 (`python-knps-api`): 트래킹 / 안전
- 산림청 (`python-krforest-api`): 휴양림
- 국가유산청 (`python-krheritage-api`): 문화재
- 한국천문연구원 (`python-kasi-api`): 일출/일몰
- VWorld (`python-vworld-api`): 경계 / 지오코딩
- Juso.go.kr (`python-kraddr-geo` 경유): 도로명/지번

본 저장소는 라이브러리 함수 호출 결과를 사용자에게 제공. provider TOS 준수는
라이브러리 책임.

처리방침에는 위탁자 명시:

- "지도 / 행정구역 데이터: 한국토지정보공사 (VWorld), 행정안전부 (도로명주소
  Juso)"
- "여행 정보: 한국관광공사 (TourAPI), 문화체육관광부, 산림청, 국가유산청, 국립공원공단"
- "날씨: 기상청"
- "유가: 한국석유공사"
- "휴게소: 한국도로공사"
- "해양: 국립해양조사원"
- "대기질: 환경공단"

(모두 국내 정부/공공기관 — 국외 이전 의무 발생 안 함)

## 4. 데이터 캐싱 정책

- 같은 (region, time window) 외부 API 반복 호출 X — TTL 캐시
- 클라이언트 (TanStack Query): 1분 staleTime (viewport)
- 백엔드 process LRU: 5분 (provider별 차등)
- 라이브러리 측: 별도 정책 (provider_sync_state로 증분 동기)

## 5. 다중 provider 결합 금지

- **Google Maps Content와 Kakao Map UI 결합 X** (Google TOS)
- Naver 검색 결과와 다른 지도 결합은 케이스별 검토
- 위탁자 별 응답은 사용자에 명시 (예: "Kakao Local 결과")

## 6. 로깅 / 마스킹

| 키 패턴 | 마스킹 |
|--------|--------|
| `re_*` | `[redacted-resend-key]` |
| `AIza*` | `[redacted-google-key]` |
| `\d{8,}:[A-Za-z0-9_-]{20,}` | `[redacted-telegram-token]` |
| `service[_-]?key=...` (query) | `service_key=[f]` |
| `apikey=...` | `apikey=[f]` |
| 위도/경도 정규식 (`3[3-8]\.\d+, 12[4-9]\.\d+`) | `[coord]` |

Sentry / Loki / structlog 모두 동일.

## 7. AI agent 작업 체크리스트

새 provider 통합 시:

- [ ] TOS 회의 시점 확인 + URL 메모 (PR description)
- [ ] 환경변수 + 마스킹 적용
- [ ] 본 문서에 §추가
- [ ] 처리방침 위탁자 명시 (`docs/legal/privacy-policy.md`)
- [ ] 라이브러리 위임 vs TripMate 직접 호출 결정 (ADR-005 룰)
- [ ] 캐시 정책 (TTL + 동일 region 반복 호출 차단)
- [ ] 사용자 가시 결과에 provider 라벨
- [ ] 로그 마스킹 정규식 추가
