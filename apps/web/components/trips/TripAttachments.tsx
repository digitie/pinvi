'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, Loader2, Paperclip, Trash2, Upload } from 'lucide-react';
import { ApiError, storageApi, tripApi } from '@pinvi/api-client';
import type { TripAttachmentResponse } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import {
  allowedUploadMessage,
  buildAttachmentCreate,
  contentTypeFromFile,
  isAllowedUploadFile,
  putToPresigned,
} from '@pinvi/domain';

const ATTACHMENT_ACCEPT = 'image/jpeg,image/png,image/webp,image/gif,video/mp4,application/pdf';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export interface TripAttachmentsProps {
  tripId: string;
  dayIndex?: number;
  poiId?: string;
  title?: string;
}

export function TripAttachments({ tripId, dayIndex, poiId, title = '첨부' }: TripAttachmentsProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [items, setItems] = useState<TripAttachmentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      if (poiId) {
        setItems(await tripApi(apiClient).listPoiAttachments(tripId, poiId));
      } else if (dayIndex != null) {
        setItems(await tripApi(apiClient).listDayAttachments(tripId, dayIndex));
      } else {
        setItems(await tripApi(apiClient).listAttachments(tripId));
      }
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '첨부를 불러오지 못했습니다.');
    }
  }, [dayIndex, poiId, tripId]);

  useEffect(() => {
    let cancelled = false;
    void reload().finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [reload]);

  const onPick = async (file: File) => {
    if (file.size === 0) {
      setError('빈 파일은 업로드할 수 없습니다.');
      return;
    }
    if (!isAllowedUploadFile(file)) {
      setError(allowedUploadMessage());
      return;
    }
    const contentType = contentTypeFromFile(file);
    setUploading(true);
    setError(null);
    try {
      const up = await storageApi(apiClient).createUploadUrl({
        filename: file.name,
        content_type: contentType,
        content_length: file.size,
        purpose: poiId
          ? 'poi_attachment'
          : dayIndex != null
            ? 'trip_day_attachment'
            : 'trip_attachment',
      });
      await putToPresigned(up, file);
      if (poiId) {
        await tripApi(apiClient).createPoiAttachment(
          tripId,
          poiId,
          buildAttachmentCreate(up, file),
        );
      } else if (dayIndex != null) {
        await tripApi(apiClient).createDayAttachment(
          tripId,
          dayIndex,
          buildAttachmentCreate(up, file),
        );
      } else {
        await tripApi(apiClient).createAttachment(tripId, buildAttachmentCreate(up, file));
      }
      await reload();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : '업로드에 실패했습니다.',
      );
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  const download = async (attachmentId: string) => {
    setBusyId(attachmentId);
    setError(null);
    try {
      const res = poiId
        ? await tripApi(apiClient).poiAttachmentDownloadUrl(tripId, poiId, attachmentId)
        : dayIndex != null
          ? await tripApi(apiClient).dayAttachmentDownloadUrl(tripId, dayIndex, attachmentId)
          : await tripApi(apiClient).attachmentDownloadUrl(tripId, attachmentId);
      window.open(res.download_url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '다운로드 링크를 만들지 못했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (attachmentId: string) => {
    setBusyId(attachmentId);
    setError(null);
    try {
      if (poiId) {
        await tripApi(apiClient).deletePoiAttachment(tripId, poiId, attachmentId);
      } else if (dayIndex != null) {
        await tripApi(apiClient).deleteDayAttachment(tripId, dayIndex, attachmentId);
      } else {
        await tripApi(apiClient).deleteAttachment(tripId, attachmentId);
      }
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '삭제에 실패했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-3 rounded-sm border border-hairline bg-white p-4" aria-label="첨부">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-bold text-ink">
          <Paperclip className="h-4 w-4 text-primary" aria-hidden="true" />
          {title}
        </h2>
        <label className="inline-flex h-9 cursor-pointer items-center gap-1 rounded-sm bg-primary px-3 text-sm font-semibold text-white hover:opacity-90">
          {uploading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Upload className="h-4 w-4" aria-hidden="true" />
          )}
          파일 올리기
          <input
            ref={inputRef}
            type="file"
            accept={ATTACHMENT_ACCEPT}
            className="sr-only"
            data-testid="attachment-input"
            disabled={uploading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void onPick(file);
            }}
          />
        </label>
      </div>

      {error && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">
          {error}
        </p>
      )}

      {loading ? (
        <div className="flex h-16 items-center justify-center text-sm text-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          불러오는 중…
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-sm bg-surface-soft px-3 py-2 text-sm text-muted">첨부가 없습니다.</p>
      ) : (
        <ul className="space-y-1" data-testid="trip-attachment-list">
          {items.map((item) => (
            <li
              key={item.attachment_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-hairline px-3 py-2 text-sm"
            >
              <span className="min-w-0">
                <span className="block truncate font-medium text-ink">
                  {item.original_filename}
                </span>
                <span className="text-xs text-muted">
                  {item.content_type} · {formatBytes(item.byte_size)}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => void download(item.attachment_id)}
                  disabled={busyId === item.attachment_id}
                  aria-label="다운로드"
                  className="rounded-sm p-1.5 text-muted hover:bg-surface-soft hover:text-ink disabled:opacity-50"
                >
                  <Download className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => void remove(item.attachment_id)}
                  disabled={busyId === item.attachment_id}
                  aria-label="삭제"
                  className="rounded-sm p-1.5 text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
