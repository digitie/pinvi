import { z } from 'zod';

/** ISO 8601 + offset. Pydantic의 `datetime` 직렬화와 동일. */
export const Iso8601Schema = z.string().datetime({ offset: true });

/** Pydantic `Decimal` JSON 직렬화 응답 — 금액 정밀도 보존을 위해 string으로 받는다. */
export const NonNegativeDecimalStringSchema = z.string().regex(/^(?:0|[1-9]\d*)(?:\.\d+)?$/);

/**
 * EPSG:4326 좌표 입력 유효 범위 — `(lon, lat)` 순서. **한반도 전체를 덮는 사각형**이다.
 *
 * 이것은 "이 값이 좌표로서 말이 되는가"를 보는 입력 검증이지 서비스 지역 판정이 아니다.
 * lat 상한 43은 한반도 북단(온성 43.0)까지 포함하므로 북한 좌표도 통과한다 — 서비스 지역인지
 * 물으려면 `isInServiceArea`를 써라(ADR-064).
 */
export const COORD_INPUT_BOUNDS = {
  lonMin: 124,
  lonMax: 132,
  latMin: 33,
  latMax: 43,
} as const;

export const CoordSchema = z.object({
  lon: z.number().min(COORD_INPUT_BOUNDS.lonMin).max(COORD_INPUT_BOUNDS.lonMax),
  lat: z.number().min(COORD_INPUT_BOUNDS.latMin).max(COORD_INPUT_BOUNDS.latMax),
});
export type Coord = z.infer<typeof CoordSchema>;

/**
 * Pinvi가 실제로 서비스하는 범위 — 남한. lat 상한 39.5는 저장소가 이미 여러 곳에서 쓰던 값이다
 * (`new_place` 제안 검증, cache target CheckConstraint 등). 여기서 이름을 붙여 정본으로 삼는다.
 *
 * **사각형으로는 정확할 수 없다.** 이 함수는 lat > 39.5(신의주·함흥·청진)와 명백한 국외만
 * 걸러낸다. 대마도(lon 129.2~129.5, lat 34.0~34.7)와 평양(39.03)·개성(37.97)은 통과한다.
 * 그리고 이건 상한을 조여도 고쳐지지 않는다 — **개성(37.97)이 강원 고성(38.38)보다 남쪽이라
 * 어떤 위도선도 남북한을 가르지 못한다.** 사각형은 이 문제에 맞는 도구가 아니다.
 *
 * 그래서 이 함수는 "국내인가"를 답한다고 주장하지 않는다. 답하는 것은 "지도를 사용자 위치로
 * 옮길 만한 좌표인가"이고, 틀렸을 때의 결과는 빈 지도를 보는 것뿐이다. 정확한 판정이 필요하면
 * (좌표 기반 차단 등) kor-travel-geo의 행정구역 조회를 써야 한다 — 근거는 ADR-064.
 */
export const SERVICE_AREA_BOUNDS = {
  lonMin: 124,
  lonMax: 132,
  latMin: 33,
  latMax: 39.5,
} as const;

export function isInServiceArea(coord: { lon: number; lat: number }): boolean {
  return (
    coord.lon >= SERVICE_AREA_BOUNDS.lonMin &&
    coord.lon <= SERVICE_AREA_BOUNDS.lonMax &&
    coord.lat >= SERVICE_AREA_BOUNDS.latMin &&
    coord.lat <= SERVICE_AREA_BOUNDS.latMax
  );
}

/**
 * 좌표의 출처 (T-329). `device`는 사용자 자신의 위치(개인위치정보)이고 `map_pick`은 사용자가
 * 지도에서 고른 지점이다. 서버는 `device`에만 위치 동의를 요구한다 — `map_pick`까지 막으면
 * 동의와 무관한 지도 기능이 깨진다. 정본 정의는 `apps/api/app/core/coord_source.py`.
 */
export const CoordSourceSchema = z.enum(['device', 'map_pick']);
export type CoordSource = z.infer<typeof CoordSourceSchema>;

/** API 공통 성공 응답 wrapper. */
export const SuccessEnvelopeSchema = <T extends z.ZodTypeAny>(data: T) =>
  z.object({
    data,
    meta: z
      .object({
        cursor: z.string().nullable().optional(),
        has_more: z.boolean().nullable().optional(),
        total: z.number().int().nullable().optional(),
        page: z.number().int().nullable().optional(),
        limit: z.number().int().nullable().optional(),
        version: z.number().int().nullable().optional(),
      })
      .partial()
      .optional(),
  });

/** API 공통 실패 응답. */
export const ErrorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.record(z.string(), z.unknown()).optional(),
  }),
});
export type ErrorEnvelope = z.infer<typeof ErrorEnvelopeSchema>;
