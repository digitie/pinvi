'use client';

import { useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys, storageApi } from '@pinvi/api-client';
import { buildAttachmentCreate, putToPresigned } from '@pinvi/domain';
import type { AttachmentResponse } from '@pinvi/schemas';
import { ExternalLink, Loader2, Paperclip, Trash2, Upload } from 'lucide-react';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export interface NoticeAttachmentPanelProps {
  planId: string;
  poiId?: string;
  title?: string;
}

export function NoticeAttachmentPanel({
  planId,
  poiId,
  title = '첨부',
}: NoticeAttachmentPanelProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const queryKey = poiId
    ? queryKeys.admin.noticePoiAttachments(planId, poiId)
    : queryKeys.admin.noticePlanAttachments(planId);

  const attachmentsQuery = useQuery({
    queryKey,
    queryFn: () =>
      poiId
        ? adminApi(apiClient).listNoticePoiAttachments(planId, poiId)
        : adminApi(apiClient).listNoticePlanAttachments(planId),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey });
  };

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      if (file.size === 0) throw new Error('빈 파일은 업로드할 수 없습니다.');
      const upload = await storageApi(apiClient).createUploadUrl({
        filename: file.name,
        content_type: file.type || 'application/octet-stream',
        content_length: file.size,
        purpose: poiId ? 'curated_poi_attachment' : 'curated_plan_attachment',
      });
      await putToPresigned(upload, file);
      const body = buildAttachmentCreate(upload, file);
      return poiId
        ? adminApi(apiClient).createNoticePoiAttachment(planId, poiId, body)
        : adminApi(apiClient).createNoticePlanAttachment(planId, body);
    },
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err) => {
      setError(
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : '업로드 실패',
      );
    },
    onSettled: () => {
      if (inputRef.current) inputRef.current.value = '';
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (attachment: AttachmentResponse) =>
      poiId
        ? adminApi(apiClient).deleteNoticePoiAttachment(planId, poiId, attachment.attachment_id)
        : adminApi(apiClient).deleteNoticePlanAttachment(planId, attachment.attachment_id),
    onSuccess: async () => {
      setError(null);
      await invalidate();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : '첨부를 삭제하지 못했습니다.'),
  });

  const items = attachmentsQuery.data ?? [];
  const busy = uploadMutation.isPending || deleteMutation.isPending;

  return (
    <section className="space-y-3 rounded-sm border border-hairline bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <Paperclip className="h-4 w-4 text-primary" aria-hidden="true" />
          {title}
        </h2>
        <label className="inline-flex h-9 cursor-pointer items-center gap-1 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50">
          {uploadMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Upload className="h-4 w-4" aria-hidden="true" />
          )}
          파일 올리기
          <input
            ref={inputRef}
            type="file"
            className="sr-only"
            data-testid={
              poiId ? 'admin-notice-poi-attachment-input' : 'admin-notice-attachment-input'
            }
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) uploadMutation.mutate(file);
            }}
          />
        </label>
      </div>

      {(error || attachmentsQuery.isError) && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">
          {error ??
            (attachmentsQuery.error instanceof ApiError
              ? attachmentsQuery.error.message
              : '첨부를 불러오지 못했습니다.')}
        </p>
      )}

      {attachmentsQuery.isLoading ? (
        <p className="rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">불러오는 중...</p>
      ) : items.length === 0 ? (
        <p className="rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">첨부가 없습니다.</p>
      ) : (
        <ul
          className="space-y-2"
          data-testid={poiId ? 'admin-notice-poi-attachments' : 'admin-notice-attachments'}
        >
          {items.map((item) => (
            <li
              key={item.attachment_id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-sm border border-hairline px-3 py-2 text-sm"
            >
              <span className="min-w-0">
                <span className="block truncate font-medium text-ink">
                  {item.original_filename}
                </span>
                <span className="text-xs text-muted">
                  {item.content_type} · {formatBytes(item.byte_size)}
                </span>
              </span>
              {item.public_url && (
                <a
                  href={item.public_url}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`${item.original_filename} 열기`}
                  title="첨부 열기"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-sm border border-hairline text-muted hover:text-ink"
                >
                  <ExternalLink className="h-4 w-4" aria-hidden="true" />
                </a>
              )}
              <button
                type="button"
                onClick={() => deleteMutation.mutate(item)}
                disabled={busy}
                className="inline-flex h-8 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold text-error-text disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                삭제
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
