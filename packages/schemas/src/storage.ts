import { z } from 'zod';
import { Iso8601Schema } from './common';

export const AttachmentPurposeSchema = z.enum([
  'media_asset',
  'avatar',
  'trip_attachment',
  'trip_day_attachment',
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

export const AvatarUploadUrlRequestSchema = UploadUrlRequestSchema.omit({
  purpose: true,
});
export type AvatarUploadUrlRequest = z.infer<typeof AvatarUploadUrlRequestSchema>;

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

/** presigned GET — private 첨부 접근(T-105). */
export const DownloadUrlResponseSchema = z.object({
  method: z.literal('GET'),
  bucket: z.string(),
  storage_key: z.string(),
  download_url: z.string().url(),
  expires_at: Iso8601Schema,
  public_url: z.string().nullable().optional(),
});
export type DownloadUrlResponse = z.infer<typeof DownloadUrlResponseSchema>;

export const AvatarApplyRequestSchema = z.object({
  bucket: z.string().min(1).max(80),
  storage_key: z.string().min(1).max(1024),
  content_type: z.string().min(1).max(255),
  byte_size: z.number().int().gt(0),
  public_url: z.string().nullable().optional(),
});
export type AvatarApplyRequest = z.infer<typeof AvatarApplyRequestSchema>;

export const AvatarInfoSchema = z.object({
  avatar_kind: z.enum(['default', 'upload', 'external']).default('default'),
  avatar_url: z.string().nullable().default(null),
  avatar_content_type: z.string().nullable().default(null),
  avatar_byte_size: z.number().int().nullable().default(null),
  avatar_updated_at: Iso8601Schema.nullable().default(null),
  has_avatar: z.boolean().default(false),
});
export type AvatarInfo = z.infer<typeof AvatarInfoSchema>;

export const AttachmentRoleSchema = z.enum(['attachment', 'image', 'document', 'reference']);
const NullableUuidSchema = z.string().uuid().nullable();

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

const AttachmentResponseBaseSchema = z
  .object({
    attachment_id: z.string().uuid(),
    trip_id: NullableUuidSchema,
    trip_day_index: z.number().int().nullable().default(null),
    trip_poi_id: NullableUuidSchema,
    curated_plan_id: NullableUuidSchema.optional(),
    curated_poi_id: NullableUuidSchema.optional(),
    notice_plan_id: NullableUuidSchema.optional(),
    notice_poi_id: NullableUuidSchema.optional(),
    source_attachment_id: NullableUuidSchema,
    bucket: z.string(),
    storage_key: z.string(),
    original_filename: z.string(),
    content_type: z.string(),
    byte_size: z.number().int(),
    public_url: z.string().nullable(),
    role: AttachmentRoleSchema,
    description: z.string().nullable(),
    sort_order: z.number().int(),
    created_at: Iso8601Schema,
    updated_at: Iso8601Schema,
  })
  .superRefine((value, ctx) => {
    if (
      value.curated_plan_id &&
      value.notice_plan_id &&
      value.curated_plan_id !== value.notice_plan_id
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['notice_plan_id'],
        message: 'notice_plan_id must match curated_plan_id',
      });
    }
    if (
      value.curated_poi_id &&
      value.notice_poi_id &&
      value.curated_poi_id !== value.notice_poi_id
    ) {
      ctx.addIssue({
        code: 'custom',
        path: ['notice_poi_id'],
        message: 'notice_poi_id must match curated_poi_id',
      });
    }
  });

export const AttachmentResponseSchema = AttachmentResponseBaseSchema.transform((value) => {
  const curatedPlanId = value.curated_plan_id ?? value.notice_plan_id ?? null;
  const curatedPoiId = value.curated_poi_id ?? value.notice_poi_id ?? null;
  return {
    ...value,
    curated_plan_id: curatedPlanId,
    curated_poi_id: curatedPoiId,
    notice_plan_id: curatedPlanId,
    notice_poi_id: curatedPoiId,
  };
});
export type AttachmentResponse = z.infer<typeof AttachmentResponseSchema>;

export const AttachmentScopeSchema = z.enum([
  'trip',
  'day',
  'poi',
  'curated_plan',
  'curated_poi',
]);
export type AttachmentScope = z.infer<typeof AttachmentScopeSchema>;

export const AttachmentLibraryItemSchema = AttachmentResponseSchema.and(
  z.object({
    target_scope: AttachmentScopeSchema,
    uploaded_by_user_id: z.string().uuid(),
    uploaded_by_email_masked: z.string().nullable().optional(),
    trip_title: z.string().nullable().optional(),
    poi_label: z.string().nullable().optional(),
  })
);
export type AttachmentLibraryItem = z.infer<typeof AttachmentLibraryItemSchema>;

export const AttachmentLibraryPageSchema = z.object({
  items: z.array(AttachmentLibraryItemSchema),
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  limit: z.number().int().positive(),
});
export type AttachmentLibraryPage = z.infer<typeof AttachmentLibraryPageSchema>;
