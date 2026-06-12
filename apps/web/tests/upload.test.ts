import { describe, expect, it } from 'vitest';
import type { UploadUrlResponse } from '@tripmate/schemas';
import { buildAttachmentCreate, roleFromContentType } from '@/lib/upload';

const up: UploadUrlResponse = {
  method: 'PUT',
  bucket: 'tripmate-media',
  storage_key: 'user-uploads/trip_attachment/u/2026/06/x.jpg',
  upload_url: 'http://127.0.0.1:12101/tripmate-media/user-uploads/x.jpg?X-Amz-Signature=z',
  headers: { 'Content-Type': 'image/jpeg' },
  expires_at: '2026-06-10T00:15:00Z',
  max_upload_bytes: 10485760,
  public_url: null,
};

describe('upload', () => {
  it('roleFromContentType: image / document / 기타', () => {
    expect(roleFromContentType('image/png')).toBe('image');
    expect(roleFromContentType('application/pdf')).toBe('document');
    expect(roleFromContentType('text/plain')).toBe('attachment');
    expect(roleFromContentType('')).toBe('attachment');
  });

  it('buildAttachmentCreate: presigned + 파일메타 → 등록 본문', () => {
    expect(buildAttachmentCreate(up, { name: 'cover.jpg', type: 'image/jpeg', size: 1024 })).toEqual({
      bucket: 'tripmate-media',
      storage_key: 'user-uploads/trip_attachment/u/2026/06/x.jpg',
      original_filename: 'cover.jpg',
      content_type: 'image/jpeg',
      byte_size: 1024,
      public_url: null,
      role: 'image',
      sort_order: 0,
    });
  });

  it('buildAttachmentCreate: 빈 content_type → octet-stream + attachment', () => {
    const res = buildAttachmentCreate(up, { name: 'data.bin', type: '', size: 5 });
    expect(res.content_type).toBe('application/octet-stream');
    expect(res.role).toBe('attachment');
  });
});
