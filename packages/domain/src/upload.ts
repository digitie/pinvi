/**
 * 첨부 2-phase 업로드 헬퍼 — `docs/api/storage.md` §3.
 *
 * (1) `POST /storage/upload-urls` → 업로드 PUT URL, (2) 브라우저가 파일 본문 PUT,
 * (3) `POST .../attachments` 로 메타 등록. 본 모듈은 (1)·(3) 사이 변환 + PUT 수행.
 */

import type { AttachmentCreate, UploadUrlResponse } from '@pinvi/schemas';

export type AttachmentRole = 'attachment' | 'image' | 'document' | 'reference';

export interface UploadFileMeta {
  name: string;
  type: string;
  size: number;
}

const EXTENSION_CONTENT_TYPES: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  gif: 'image/gif',
  mp4: 'video/mp4',
  pdf: 'application/pdf',
};

const CONTENT_TYPE_LABELS: Record<string, string> = {
  'image/jpeg': 'JPG',
  'image/png': 'PNG',
  'image/webp': 'WEBP',
  'image/gif': 'GIF',
  'video/mp4': 'MP4',
  'application/pdf': 'PDF',
};

export const IMAGE_UPLOAD_CONTENT_TYPES = new Set([
  'image/jpeg',
  'image/png',
  'image/webp',
  'image/gif',
]);

export const ATTACHMENT_UPLOAD_CONTENT_TYPES = new Set([
  ...IMAGE_UPLOAD_CONTENT_TYPES,
  'video/mp4',
  'application/pdf',
]);

export function contentTypeFromFile(file: UploadFileMeta): string {
  const contentType = file.type.trim().toLowerCase();
  if (contentType) return contentType;

  const extension = file.name.split('.').pop()?.trim().toLowerCase() ?? '';
  return EXTENSION_CONTENT_TYPES[extension] ?? 'application/octet-stream';
}

export function isAllowedUploadContentType(
  contentType: string,
  allowed = ATTACHMENT_UPLOAD_CONTENT_TYPES,
): boolean {
  return allowed.has(contentType.trim().toLowerCase());
}

export function isAllowedUploadFile(
  file: UploadFileMeta,
  allowed = ATTACHMENT_UPLOAD_CONTENT_TYPES,
): boolean {
  return isAllowedUploadContentType(contentTypeFromFile(file), allowed);
}

export function allowedUploadMessage(allowed = ATTACHMENT_UPLOAD_CONTENT_TYPES): string {
  const labels = Array.from(allowed)
    .sort()
    .map((value) => CONTENT_TYPE_LABELS[value] ?? value);
  return `업로드 가능한 파일 형식은 ${labels.join(', ')}입니다.`;
}

export function roleFromContentType(contentType: string): AttachmentRole {
  const normalized = contentType.trim().toLowerCase();
  if (normalized.startsWith('image/')) return 'image';
  if (normalized === 'application/pdf') return 'document';
  return 'attachment';
}

/** presigned 응답 + 파일 메타 → 첨부 등록 본문. */
export function buildAttachmentCreate(
  up: UploadUrlResponse,
  file: UploadFileMeta,
): AttachmentCreate {
  const contentType = contentTypeFromFile(file);
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

function uploadErrorMessage(status: number, text: string): string {
  if (text) {
    try {
      const parsed: unknown = JSON.parse(text);
      if (
        typeof parsed === 'object' &&
        parsed !== null &&
        'error' in parsed &&
        typeof parsed.error === 'object' &&
        parsed.error !== null &&
        'message' in parsed.error &&
        typeof parsed.error.message === 'string'
      ) {
        return parsed.error.message;
      }
    } catch {
      if (status >= 400 && status < 500) return text;
    }
  }
  return `파일 업로드에 실패했습니다. 다시 시도해 주세요. (HTTP ${status})`;
}

/** 업로드 URL 로 파일 본문 PUT. 실패 시 사용자에게 보여줄 수 있는 메시지로 throw. */
export async function putToPresigned(up: UploadUrlResponse, file: Blob): Promise<void> {
  let res: Response;
  try {
    res = await fetch(up.upload_url, {
      method: 'PUT',
      headers: up.headers,
      body: file,
    });
  } catch (err) {
    void err;
    throw new Error('파일 업로드 서버에 연결하지 못했습니다. 네트워크를 확인해 주세요.');
  }
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(uploadErrorMessage(res.status, text));
  }
}
