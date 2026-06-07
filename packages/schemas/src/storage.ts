import { z } from 'zod';
import { Iso8601Schema } from './common';

export const AttachmentPurposeSchema = z.enum([
  'media_asset',
  'avatar',
  'trip_attachment',
  'poi_attachment',
  'curated_plan_attachment',
  'curated_poi_attachment',
]);
export type AttachmentPurpose = z.infer<typeof AttachmentPurposeSchema>;

export const UploadUrlRequestSchema = z.object({
  filename: z.string().min(1).max(255),
  content_type: z.string().min(1).max(255),
  content_length: z.number().int().gt(0),
  purpose: AttachmentPurposeSchema,
});
export type UploadUrlRequest = z.infer<typeof UploadUrlRequestSchema>;

export const UploadUrlResponseSchema = z.object({
  method: z.literal('PUT'),
  bucket: z.string(),
  storage_key: z.string(),
  upload_url: z.string().url(),
  headers: z.record(z.string(), z.string()),
  expires_at: Iso8601Schema,
  max_upload_bytes: z.number().int(),
  public_url: z.string().nullable().optional(),
});
export type UploadUrlResponse = z.infer<typeof UploadUrlResponseSchema>;

export const AttachmentRoleSchema = z.enum(['attachment', 'image', 'document', 'reference']);

export const AttachmentCreateSchema = z.object({
  bucket: z.string().min(1).max(80),
  storage_key: z.string().min(1).max(1024),
  original_filename: z.string().min(1).max(255),
  content_type: z.string().min(1).max(255),
  byte_size: z.number().int().gt(0),
  public_url: z.string().nullable().optional(),
  checksum_sha256: z
    .string()
    .regex(/^[a-f0-9]{64}$/)
    .nullable()
    .optional(),
  role: AttachmentRoleSchema.default('attachment'),
  description: z.string().nullable().optional(),
  sort_order: z.number().int().min(0).default(0),
});
export type AttachmentCreate = z.infer<typeof AttachmentCreateSchema>;
