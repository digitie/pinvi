'use client';

import { useEffect, useState } from 'react';
import { Download, Loader2, Trash2 } from 'lucide-react';
import { ApiError, authApi } from '@pinvi/api-client';
import type { AttachmentLibraryItem } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const scopeLabel: Record<AttachmentLibraryItem['target_scope'], string> = {
  trip: '여행',
  day: '날짜',
  poi: '장소',
  curated_plan: '추천 계획',
  curated_poi: '추천 장소',
};

export default function MyFilesPage() {
  const [items, setItems] = useState<AttachmentLibraryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    const page = await authApi(apiClient).listFiles({ limit: 100 });
    setItems(page.items);
    setTotal(page.total);
  };

  useEffect(() => {
    let cancelled = false;
    void reload()
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : '파일을 불러오지 못했습니다.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const download = async (attachmentId: string) => {
    setBusyId(attachmentId);
    setError(null);
    try {
      const res = await authApi(apiClient).fileDownloadUrl(attachmentId);
      window.open(res.download_url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '다운로드 링크를 만들지 못했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (attachmentId: string) => {
    if (!window.confirm('이 파일 연결을 삭제할까요?')) return;
    setBusyId(attachmentId);
    setError(null);
    try {
      await authApi(apiClient).deleteFile(attachmentId);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '삭제하지 못했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-ink">파일</h1>
        <p className="mt-1 text-sm text-muted">{total.toLocaleString('ko-KR')}개</p>
      </div>

      {error && <p className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">{error}</p>}

      {loading ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          불러오는 중...
        </div>
      ) : items.length === 0 ? (
        <p className="rounded-sm border border-hairline bg-white p-5 text-sm text-muted">
          업로드한 파일이 없습니다.
        </p>
      ) : (
        <div className="overflow-hidden rounded-sm border border-hairline bg-white">
          <ul className="divide-y divide-hairline" data-testid="my-file-list">
            {items.map((item) => (
              <li
                key={item.attachment_id}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-ink">
                    {item.original_filename}
                  </span>
                  <span className="text-xs text-muted">
                    {scopeLabel[item.target_scope]} · {item.trip_title ?? item.poi_label ?? '—'} ·{' '}
                    {formatBytes(item.byte_size)}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => void download(item.attachment_id)}
                    disabled={busyId === item.attachment_id}
                    aria-label="다운로드"
                    className="rounded-sm p-2 text-muted hover:bg-surface-soft hover:text-ink disabled:opacity-50"
                  >
                    <Download className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void remove(item.attachment_id)}
                    disabled={busyId === item.attachment_id}
                    aria-label="삭제"
                    className="rounded-sm p-2 text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
