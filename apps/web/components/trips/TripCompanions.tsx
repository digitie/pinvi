'use client';

import { useState } from 'react';
import { Loader2, UserPlus, Users, X } from 'lucide-react';
import { ApiError, tripApi } from '@pinvi/api-client';
import type { TripCompanionResponse, TripCompanionRole } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { ROLE_LABEL, companionDisplayName, companionJoined } from '@/lib/companion';

const ROLES: TripCompanionRole[] = ['editor', 'viewer', 'co_owner'];

export interface TripCompanionsProps {
  tripId: string;
  companions: TripCompanionResponse[];
  onChanged: () => void | Promise<unknown>;
}

export function TripCompanions({ tripId, companions, onChanged }: TripCompanionsProps) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<TripCompanionRole>('editor');
  const [inviting, setInviting] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const invite = async () => {
    const trimmed = email.trim();
    if (!trimmed) {
      setError('이메일을 입력하세요.');
      return;
    }
    setInviting(true);
    setError(null);
    try {
      await tripApi(apiClient).inviteMember(tripId, { email: trimmed, role });
      setEmail('');
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '초대에 실패했습니다.');
    } finally {
      setInviting(false);
    }
  };

  const remove = async (companionId: string) => {
    setBusyId(companionId);
    setError(null);
    try {
      await tripApi(apiClient).removeMember(tripId, companionId);
      await onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '제거에 실패했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-3 rounded-sm border border-hairline bg-white p-4" aria-label="동반자">
      <h2 className="flex items-center gap-2 text-sm font-bold text-ink">
        <Users className="h-4 w-4 text-primary" aria-hidden="true" />
        동반자 ({companions.length})
      </h2>

      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-40 flex-1 text-xs font-semibold text-ink">
          이메일
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="friend@example.com"
            className="mt-1 block h-9 w-full rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
          />
        </label>
        <label className="text-xs font-semibold text-ink">
          권한
          <select
            value={role}
            onChange={(event) => setRole(event.target.value as TripCompanionRole)}
            className="mt-1 block h-9 rounded-sm border border-hairline px-2 text-sm font-normal text-ink outline-none focus:border-primary"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void invite()}
          disabled={inviting || !email.trim()}
          className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50"
        >
          {inviting ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <UserPlus className="h-4 w-4" aria-hidden="true" />
          )}
          초대
        </button>
      </div>

      {error && <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">{error}</p>}

      {companions.length > 0 && (
        <ul className="space-y-1" data-testid="companion-list">
          {companions.map((companion) => (
            <li
              key={companion.companion_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-hairline px-3 py-2 text-sm"
            >
              <span className="flex items-center gap-2 text-ink">
                <span className="font-medium">{companionDisplayName(companion)}</span>
                <span className="rounded-sm bg-surface-soft px-1.5 py-0.5 text-xs text-muted">
                  {ROLE_LABEL[companion.role]}
                </span>
                <span className="text-xs text-muted">
                  {companionJoined(companion) ? '참여' : '초대됨'}
                </span>
              </span>
              <button
                type="button"
                onClick={() => void remove(companion.companion_id)}
                disabled={busyId === companion.companion_id}
                aria-label="동반자 제거"
                className="inline-flex h-7 items-center gap-1 rounded-sm border border-hairline px-2 text-xs font-semibold text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
              >
                {busyId === companion.companion_id ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                ) : (
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                제거
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
