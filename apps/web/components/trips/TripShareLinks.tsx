'use client';

import { useState } from 'react';
import { Copy, Link2, Loader2, Trash2 } from 'lucide-react';
import { ApiError, tripApi } from '@tripmate/api-client';
import type { TripShareLinkVisibility, TripViewShareLink } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import { SHARE_STATUS_LABEL, VISIBILITY_LABEL, shareLinkStatus } from '@/lib/shareLink';

const VISIBILITIES: TripShareLinkVisibility[] = ['view_only', 'comment', 'edit'];

function formatDate(value: string | null): string {
  if (!value) return '무기한';
  return new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium' }).format(new Date(value));
}

export interface TripShareLinksProps {
  tripId: string;
  shareLinks: TripViewShareLink[];
  onChanged: () => void | Promise<unknown>;
}

export function TripShareLinks({ tripId, shareLinks, onChanged }: TripShareLinksProps) {
  const [visibility, setVisibility] = useState<TripShareLinkVisibility>('view_only');
  const [expiresAt, setExpiresAt] = useState('');
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [newUrl, setNewUrl] = useState<string | null>(null);

  const create = async () => {
    setCreating(true);
    setError(null);
    setNewUrl(null);
    try {
      const res = await tripApi(apiClient).createShareToken(tripId, {
        visibility,
        expires_at: expiresAt ? new Date(`${expiresAt}T23:59:59`).toISOString() : null,
      });
      setNewUrl(res.url);
      setExpiresAt('');
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '공유 링크를 만들지 못했습니다.');
    } finally {
      setCreating(false);
    }
  };

  const revoke = async (shareId: string) => {
    setRevokingId(shareId);
    setError(null);
    try {
      await tripApi(apiClient).revokeShareToken(tripId, shareId);
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '철회에 실패했습니다.');
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <section className="space-y-3 rounded-sm border border-hairline bg-white p-4" aria-label="공유 링크">
      <h2 className="flex items-center gap-2 text-sm font-bold text-ink">
        <Link2 className="h-4 w-4 text-primary" aria-hidden="true" />
        공유 링크
      </h2>

      <div className="flex flex-wrap items-end gap-2">
        <label className="text-xs font-semibold text-ink">
          권한
          <select
            value={visibility}
            onChange={(event) => setVisibility(event.target.value as TripShareLinkVisibility)}
            className="mt-1 block h-9 rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
          >
            {VISIBILITIES.map((v) => (
              <option key={v} value={v}>
                {VISIBILITY_LABEL[v]}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs font-semibold text-ink">
          만료일(선택)
          <input
            type="date"
            value={expiresAt}
            onChange={(event) => setExpiresAt(event.target.value)}
            className="mt-1 block h-9 rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
          />
        </label>
        <button
          type="button"
          onClick={() => void create()}
          disabled={creating}
          className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          {creating && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
          링크 만들기
        </button>
      </div>

      {error && <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">{error}</p>}

      {newUrl && (
        <div className="space-y-1 rounded-sm bg-success-bg px-3 py-2" data-testid="new-share-url">
          <p className="text-xs font-semibold text-success-text">
            링크가 생성됐습니다. 이 주소는 지금만 표시됩니다.
          </p>
          <div className="flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate text-xs text-ink">{newUrl}</code>
            <button
              type="button"
              onClick={() => void navigator.clipboard?.writeText(newUrl)}
              aria-label="링크 복사"
              className="inline-flex h-7 items-center gap-1 rounded-sm border border-hairline bg-white px-2 text-xs font-semibold text-ink hover:bg-surface-soft"
            >
              <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              복사
            </button>
          </div>
        </div>
      )}

      {shareLinks.length > 0 && (
        <ul className="space-y-1" data-testid="share-link-list">
          {shareLinks.map((link) => {
            const status = shareLinkStatus(link);
            return (
              <li
                key={link.share_id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-hairline px-3 py-2 text-sm"
              >
                <span className="flex items-center gap-2 text-ink">
                  <span className="font-medium">{VISIBILITY_LABEL[link.visibility]}</span>
                  <span className="rounded-sm bg-surface-soft px-1.5 py-0.5 text-xs text-muted">
                    {SHARE_STATUS_LABEL[status]}
                  </span>
                  <span className="text-xs text-muted">만료 {formatDate(link.expires_at)}</span>
                </span>
                {status === 'active' && (
                  <button
                    type="button"
                    onClick={() => void revoke(link.share_id)}
                    disabled={revokingId === link.share_id}
                    aria-label="공유 링크 철회"
                    className="inline-flex h-7 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
                  >
                    {revokingId === link.share_id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    )}
                    철회
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
