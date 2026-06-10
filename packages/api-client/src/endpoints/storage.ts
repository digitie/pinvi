import { UploadUrlRequestSchema, UploadUrlResponseSchema } from '@tripmate/schemas';
import type { ApiClient } from '../client';
import type { UploadUrlRequest } from '@tripmate/schemas';

/** `docs/api/storage.md` §4 — presigned PUT 발급. */
export const storageApi = (client: ApiClient) => ({
  createUploadUrl: (body: UploadUrlRequest) =>
    client.request('/storage/upload-urls', {
      method: 'POST',
      body: JSON.stringify(UploadUrlRequestSchema.parse(body)),
      schema: UploadUrlResponseSchema,
    }),
});
