'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ApiClient, ApiError, adminApi } from '@pinvi/api-client';
import type { AdminTripDetail, TripStatus } from '@pinvi/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { FormTextArea } from '@/components/forms/FormTextArea';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12501',
});

const STATUSES: { value: TripStatus; label: string }[] = [
  { value: 'draft', label: '초안' },
  { value: 'planned', label: '계획' },
  { value: 'in_progress', label: '진행' },
  { value: 'completed', label: '완료' },
  { value: 'archived', label: '보관' },
];

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleDateString('ko-KR') : '—';

const formatDateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

export default function AdminTripDetailPage() {
  const router = useRouter();
  const params = useParams<{ trip_id: string }>();
  const tripId = params.trip_id;
  const [trip, setTrip] = useState<AdminTripDetail | null>(null);
  const [statusDraft, setStatusDraft] = useState<TripStatus>('draft');
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [showStatusDialog, setShowStatusDialog] = useState(false);
  const [acting, setActing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    adminApi(apiClient)
      .getTrip(tripId)
      .then((res) => {
        if (cancelled) return;
        setTrip(res);
        setStatusDraft(res.status);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          router.replace('/admin/trips');
          return;
        }
        setError(err instanceof ApiError ? err.message : '조회 실패');
      });
    return () => {
      cancelled = true;
    };
  }, [router, tripId]);

  const onStatusSave = async () => {
    if (!trip || reason.trim().length < 1) return;
    setActing(true);
    try {
      const updated = await adminApi(apiClient).updateTripStatus(trip.trip_id, {
        status: statusDraft,
        access_reason: reason.trim(),
      });
      setTrip(updated);
      setStatusDraft(updated.status);
      setShowStatusDialog(false);
      setReason('');
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '상태 변경 실패');
    } finally {
      setActing(false);
    }
  };

  if (error) {
    return (
      <AdminPage title="여행 상세">
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      </AdminPage>
    );
  }

  if (!trip) {
    return (
      <AdminPage title="여행 상세">
        <p className="text-sm text-muted">불러오는 중...</p>
      </AdminPage>
    );
  }

  const period =
    trip.start_date === trip.end_date
      ? formatDate(trip.start_date)
      : `${formatDate(trip.start_date)} ~ ${formatDate(trip.end_date)}`;

  return (
    <AdminPage
      title={trip.title}
      description={`trip_id ${trip.trip_id}`}
      actions={
        <Link href="/admin/trips" className="rounded-sm border border-hairline px-3 py-2 text-sm">
          목록으로
        </Link>
      }
    >
      <Section title="기본 정보">
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2" data-testid="admin-trip-info">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">소유자</dt>
            <dd className="font-mono">{trip.owner_email_masked}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">owner_user_id</dt>
            <dd className="font-mono text-xs">{trip.owner_user_id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">상태</dt>
            <dd className="mt-1 flex flex-wrap items-center gap-2">
              <select
                value={statusDraft}
                onChange={(e) => setStatusDraft(e.target.value as TripStatus)}
                className="rounded-sm border border-hairline px-2 py-1 text-sm"
                data-testid="admin-trip-status-select"
              >
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                disabled={statusDraft === trip.status}
                onClick={() => setShowStatusDialog(true)}
                className="rounded-sm border border-primary px-3 py-1 text-sm text-primary disabled:opacity-50"
                data-testid="admin-trip-status-save"
              >
                저장
              </button>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">공개</dt>
            <dd>{trip.visibility}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">지역</dt>
            <dd>{trip.region_hint ?? trip.primary_region_code ?? '—'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">기간</dt>
            <dd>{period}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">구성</dt>
            <dd>
              days {trip.day_count} / POI {trip.poi_count} / companions {trip.companion_count} /
              shares {trip.share_link_count}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">version</dt>
            <dd>{trip.version}</dd>
          </div>
        </dl>
        {trip.description && <p className="mt-4 text-sm text-ink">{trip.description}</p>}
      </Section>

      <Section title="동반자">
        <div className="overflow-x-auto" data-testid="admin-trip-companions">
          <table className="min-w-full divide-y divide-hairline text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-2">초대 이메일</th>
                <th className="px-2 py-2">닉네임</th>
                <th className="px-2 py-2">역할</th>
                <th className="px-2 py-2">가입</th>
                <th className="px-2 py-2">초대</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {trip.companions.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-2 py-4 text-center text-muted">
                    항목이 없습니다.
                  </td>
                </tr>
              ) : (
                trip.companions.map((row) => (
                  <tr key={row.companion_id}>
                    <td className="px-2 py-2 font-mono text-xs">
                      {row.invited_email_masked ?? '—'}
                    </td>
                    <td className="px-2 py-2">{row.invited_nickname ?? '—'}</td>
                    <td className="px-2 py-2">{row.role}</td>
                    <td className="px-2 py-2">{formatDateTime(row.joined_at)}</td>
                    <td className="px-2 py-2">{formatDateTime(row.invited_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="공유 링크">
        <div className="overflow-x-auto" data-testid="admin-trip-share-links">
          <table className="min-w-full divide-y divide-hairline text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-2">share_id</th>
                <th className="px-2 py-2">권한</th>
                <th className="px-2 py-2">만료</th>
                <th className="px-2 py-2">폐기</th>
                <th className="px-2 py-2">마지막 사용</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {trip.share_links.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-2 py-4 text-center text-muted">
                    항목이 없습니다.
                  </td>
                </tr>
              ) : (
                trip.share_links.map((row) => (
                  <tr key={row.share_id}>
                    <td className="px-2 py-2 font-mono text-xs">{row.share_id}</td>
                    <td className="px-2 py-2">{row.visibility}</td>
                    <td className="px-2 py-2">{formatDateTime(row.expires_at)}</td>
                    <td className="px-2 py-2">{formatDateTime(row.revoked_at)}</td>
                    <td className="px-2 py-2">{formatDateTime(row.last_used_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="최근 Audit">
        <div className="overflow-x-auto" data-testid="admin-trip-audit-list">
          <table className="min-w-full divide-y divide-hairline text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-2">액션</th>
                <th className="px-2 py-2">사유</th>
                <th className="px-2 py-2">시각</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {trip.recent_audit.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-2 py-4 text-center text-muted">
                    기록이 없습니다.
                  </td>
                </tr>
              ) : (
                trip.recent_audit.map((row) => (
                  <tr key={row.log_id}>
                    <td className="px-2 py-2 font-mono text-xs">{row.action}</td>
                    <td className="px-2 py-2">{row.access_reason ?? '—'}</td>
                    <td className="px-2 py-2">{formatDateTime(row.occurred_at)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Section>

      {showStatusDialog && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md space-y-4 rounded-sm bg-white p-6">
            <h3 className="text-lg font-bold text-ink">여행 상태 변경</h3>
            <p className="text-xs text-muted">
              {trip.status} → {statusDraft}
            </p>
            <FormTextArea
              id="admin-trip-action-reason"
              label="사유"
              hint="감사 로그에 기록됩니다."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              data-testid="admin-trip-action-reason"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowStatusDialog(false);
                  setReason('');
                }}
                className="rounded-sm border border-hairline px-3 py-2 text-sm"
              >
                취소
              </button>
              <button
                type="button"
                disabled={acting || reason.trim().length < 1}
                onClick={onStatusSave}
                className="rounded-sm bg-primary px-3 py-2 text-sm text-white disabled:opacity-50"
                data-testid="admin-trip-action-confirm"
              >
                {acting ? '처리 중...' : '확인'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AdminPage>
  );
}
