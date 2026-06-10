/**
 * 첨부 2-phase 업로드 헬퍼 — `docs/api/storage.md` §3.
 *
 * (1) `POST /storage/upload-urls` → presigned PUT, (2) 브라우저가 RustFS 로 직접 PUT,
 * (3) `POST .../attachments` 로 메타 등록. 본 모듈은 (1)·(3) 사이 변환 + PUT 수행.
 */

import type { AttachmentCreate, UploadUrlResponse } from '@tripmate/schemas';

export type AttachmentRole = 'attachment' | 'image' | 'document' | 'reference';

export interface UploadFileMeta {
  name: string;
  type: string;
  size: number;
}

export function roleFromContentType(contentType: string): AttachmentRole {
  if (contentType.startsWith('image/')) return 'image';
  if (contentType === 'application/pdf') return 'document';
  return 'attachment';
}

/** presigned 응답 + 파일 메타 → 첨부 등록 본문. */
export function buildAttachmentCreate(
  up: UploadUrlResponse,
  file: UploadFileMeta
): AttachmentCreate {
  const contentType = file.type || 'application/octet-stream';
  return {
    bucket: up.bucket,
    storage_key: up.storage_key,
    original_filename: file.name,
    content_type: contentType,
    byte_size: file.size,
    public_url: up.public_url ?? null,
    role: roleFromContentType(contentType),
    sort_order: 0,
  };
}

/** presigned URL 로 파일 본문 PUT(브라우저 → RustFS). 실패 시 throw. */
export async function putToPresigned(up: UploadUrlResponse, file: Blob): Promise<void> {
  const res = await fetch(up.upload_url, {
    method: 'PUT',
    headers: up.headers,
    body: file,
  });
  if (!res.ok) {
    throw new Error(`업로드 실패(HTTP ${res.status})`);
  }
}
