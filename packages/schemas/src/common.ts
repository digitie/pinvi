import { z } from 'zod';

/** ISO 8601 + offset. Pydantic의 `datetime` 직렬화와 동일. */
export const Iso8601Schema = z.string().datetime({ offset: true });

/** EPSG:4326 좌표 — `(longitude, latitude)` 순서, 대한민국 범위. */
export const CoordSchema = z.object({
  longitude: z.number().min(124).max(132),
  latitude: z.number().min(33).max(43),
});
export type Coord = z.infer<typeof CoordSchema>;

/** API 공통 성공 응답 wrapper. */
export const SuccessEnvelopeSchema = <T extends z.ZodTypeAny>(data: T) =>
  z.object({
    data,
    meta: z
      .object({
        cursor: z.string().nullable().optional(),
        has_more: z.boolean().optional(),
        total: z.number().int().optional(),
        page: z.number().int().optional(),
        limit: z.number().int().optional(),
        version: z.number().int().optional(),
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
