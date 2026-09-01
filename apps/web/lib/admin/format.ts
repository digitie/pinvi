/**
 * KTM `packages/kor-travel-map-admin/frontend/src/lib/format.ts`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분과 이유:
 *  - 맨 위 `// Hallmark · genre: …` 마커 주석 제거 — KTM 디자인 시스템(`design.md`) 전용 표식.
 *  - 문자열 리터럴 따옴표만 pinvi prettier 설정(`singleQuote: true`)에 맞춰 작은따옴표로 바꿨다.
 *    `NULL_GLYPH`(U+2014 em dash)와 `shortId`의 ASCII `...` 말줄임은 값 계약이라 그대로다.
 *  - `shortId` 주석이 참조하던 e2e spec 경로는 KTM 것임을 명시했다(pinvi에는 없다).
 *  - 로직·시그니처·기본값은 원문 그대로다.
 *
 * 주의: pinvi에는 `formatDateTime`이 이미 여러 파일에 중복 정의돼 있다. 이 파일은 admin 표면 전용
 * 사본이며, 기존 정의를 이 파일로 모으는 정리는 후속 단계에서 한다(지금 건드리지 않는다).
 * 또 KTM 규약상 `number` 입력은 **초 단위 epoch**로 해석한다(`value * 1000`) — ms epoch을 넘기면
 * 엉뚱한 시각이 나오므로 호출부에서 단위를 맞춘다.
 *
 * ── 이하 원문 문서 주석 ──
 *
 * 표시용 포맷 유틸(design.md §Copy).
 *
 * - 빈 값 글리프는 `NULL_GLYPH`(U+2014 em dash) 하나만 쓴다 — `-`(hyphen) 금지.
 * - `formatCount`는 미지 값(null/undefined) 또는 loading 중에 `—`를 돌려준다.
 *   숫자를 0으로 coalesce하지 않는다(가짜 0 = "all clear"로 읽힘, M36).
 */

/** 빈 값/미지 값 글리프. `-`가 아니라 em dash. */
export const NULL_GLYPH = '—';

const dateTimeFormatter = new Intl.DateTimeFormat('ko-KR', {
  dateStyle: 'short',
  timeStyle: 'medium',
});

const compactNumberFormatter = new Intl.NumberFormat('ko-KR');

export function formatDateTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined) {
    return NULL_GLYPH;
  }
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  if (Number.isNaN(date.getTime())) {
    return NULL_GLYPH;
  }
  return dateTimeFormatter.format(date);
}

export interface FormatCountOptions {
  /** query가 아직 resolve되지 않았으면 true — 값이 있어도 `—`를 돌려준다. */
  loading?: boolean;
}

/**
 * 정수/실수를 ko-KR 천 단위 구분으로 표기한다. null/undefined/NaN 또는 `loading`이면
 * `—`(NULL_GLYPH) — 절대 가짜 0을 만들지 않는다.
 */
export function formatCount(
  value: number | null | undefined,
  options: FormatCountOptions = {},
): string {
  if (options.loading) {
    return NULL_GLYPH;
  }
  if (value === null || value === undefined || Number.isNaN(value)) {
    return NULL_GLYPH;
  }
  return compactNumberFormatter.format(value);
}

/**
 * 긴 식별자를 앞 `size`자로 자른다. 빈 값은 `—`.
 * 말줄임은 ASCII `...`를 유지한다 — KTM e2e/consistency-drilldown.spec.ts가
 * `slice(0, 12) + "..."`를 단언하므로 그 계약이 바뀌기 전까지 U+2026로 바꾸지 않는다.
 */
export function shortId(value: string | null | undefined, size = 12): string {
  if (!value) {
    return NULL_GLYPH;
  }
  return value.length > size ? `${value.slice(0, size)}...` : value;
}
