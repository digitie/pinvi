import { z } from 'zod';
import { Iso8601Schema } from './common';

/** `docs/api/trips.md`. */
export const TripStatusSchema = z.enum([
  'draft',
  'planned',
  'in_progress',
  'completed',
  'archived',
]);
export const TripVisibilitySchema = z.enum(['private', 'unlisted', 'public']);
export type TripStatus = z.infer<typeof TripStatusSchema>;
export type TripVisibility = z.infer<typeof TripVisibilitySchema>;

export const TripCompanionInviteSchema = z.object({
  email: z.string().email().max(320),
  display_name: z.string().max(80).nullable().optional(),
  role: z.enum(['co_owner', 'editor', 'viewer']).default('editor'),
});

export const TripCreateSchema = z.object({
  title: z.string().min(1).max(200),
  description: z.string().nullable().optional(),
  region_hint: z.string().max(120).nullable().optional(),
  start_date: z.string().date().nullable().optional(),
  end_date: z.string().date().nullable().optional(),
  visibility: TripVisibilitySchema.default('private'),
  companions: z.array(TripCompanionInviteSchema).default([]),
});
export type TripCreate = z.infer<typeof TripCreateSchema>;

export const TripUpdateSchema = z.object({
  title: z.string().min(1).max(200).optional(),
  description: z.string().nullable().optional(),
  region_hint: z.string().max(120).nullable().optional(),
  cover_attachment_id: z.string().uuid().nullable().optional(),
  start_date: z.string().date().nullable().optional(),
  end_date: z.string().date().nullable().optional(),
  visibility: TripVisibilitySchema.optional(),
  status: TripStatusSchema.optional(),
});
export type TripUpdate = z.infer<typeof TripUpdateSchema>;

export const TripResponseSchema = z.object({
  trip_id: z.string().uuid(),
  owner_user_id: z.string().uuid(),
  title: z.string(),
  description: z.string().nullable(),
  region_hint: z.string().nullable(),
  start_date: z.string().date().nullable(),
  end_date: z.string().date().nullable(),
  visibility: TripVisibilitySchema,
  status: TripStatusSchema,
  version: z.number().int(),
  created_at: Iso8601Schema,
  updated_at: Iso8601Schema,
});
export type TripResponse = z.infer<typeof TripResponseSchema>;
