import { z } from 'zod';

/** ISO 8601 + offset. Pydantic의 `datetime` 직렬화와 동일. */
export const Iso8601Schema = z.string().datetime({ offset: true });

/** Pydantic `Decimal` JSON 직렬화 응답 — 금액 정밀도 보존을 위해 string으로 받는다. */
export const NonNegativeDecimalStringSchema = z.string().regex(/^(?:0|[1-9]\d*)(?:\.\d+)?$/);

/** EPSG:4326 좌표 — `(lon, lat)` 순서, 대한민국 범위. */
export const CoordSchema = z.object({
  lon: z.number().min(124).max(132),
  lat: z.number().min(33).max(43),
});
export type Coord = z.infer<typeof CoordSchema>;

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
