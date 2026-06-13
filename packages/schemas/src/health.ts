import { z } from 'zod';

export const HealthResponseSchema = z.object({
  status: z.literal('ok'),
  service: z.literal('pinvi-api'),
  version: z.string().optional(),
  git_sha: z.string().optional(),
});
export type HealthResponse = z.infer<typeof HealthResponseSchema>;

export const HealthDbResponseSchema = z.object({
  status: z.literal('ok'),
  database: z.literal('ok'),
  latency_ms: z.number().int(),
});
