'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { ApiClient, ApiError, adminApi } from '@tripmate/api-client';
import type { AdminPoiDetail } from '@tripmate/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { FormTextArea } from '@/components/forms/FormTextArea';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_TRIPMATE_API_URL ?? 'http://localhost:9021',
});

const formatDateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString('ko-KR') : '—';

const formatAmount = (value: string | null, currency: string) =>
  value === null ? '—' : `${value} ${currency}`;

const isBroken = (poi: AdminPoiDetail) => Boolean(poi.feature_link_broken_at);

export default function AdminPoiDetailPage() {
  const router = useRouter();
  const params = useParams<{ poi_id: string }>();
  const poiId = params.poi_id;
  const [poi, setPoi] = useState<AdminPoiDetail | null>(null);
  const [brokenDraft, setBrokenDraft] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [showStatusDialog, setShowStatusDialog] = useState(false);
  const [acting, setActing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    adminApi(apiClient)
      .getPoi(poiId)
      .then((res) => {
        if (cancelled) return;
        setPoi(res);
        setBrokenDraft(isBroken(res));
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          router.replace('/admin/pois');
          return;
        }
        setError(err instanceof ApiError ? err.message : '조회 실패');
      });
    return () => {
      cancelled = true;
    };
  }, [poiId, router]);

  const onLinkStatusSave = async () => {
    if (!poi || reason.trim().length < 1) return;
    setActing(true);
    try {
      const updated = await adminApi(apiClient).updatePoiLinkStatus(poi.attachment_id, {
        broken: brokenDraft,
        access_reason: reason.trim(),
      });
      setPoi(updated);
      setBrokenDraft(isBroken(updated));
      setShowStatusDialog(false);
      setReason('');
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '연결 상태 변경 실패');
    } finally {
      setActing(false);
    }
  };

  if (error) {
    return (
      <AdminPage title="POI 상세">
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      </AdminPage>
    );
  }

  if (!poi) {
    return (
      <AdminPage title="POI 상세">
        <p className="text-sm text-muted">불러오는 중...</p>
      </AdminPage>
    );
  }

  const currentBroken = isBroken(poi);
  const featureTitle = poi.feature_label ?? poi.feature_id;

  return (
    <AdminPage
      title={featureTitle}
      description={`poi_id ${poi.attachment_id}`}
      actions={
        <Link href="/admin/pois" className="rounded-sm border border-hairline px-3 py-2 text-sm">
          목록으로
        </Link>
      }
    >
      <Section title="기본 정보">
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2" data-testid="admin-poi-info">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">여행</dt>
            <dd>
              <Link href={`/admin/trips/${poi.trip_id}`} className="text-primary underline">
                {poi.trip_title}
              </Link>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">소유자</dt>
            <dd className="font-mono">{poi.owner_email_masked}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">추가자</dt>
            <dd className="font-mono">{poi.added_by_email_masked ?? poi.added_by_user_id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">일차 / 순서</dt>
            <dd>
              {poi.day_index}일차 / {poi.sort_order}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">feature_id</dt>
            <dd className="font-mono text-xs">{poi.feature_id}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">연결 상태</dt>
            <dd className="mt-1 flex flex-wrap items-center gap-2">
              <select
                value={brokenDraft ? 'broken' : 'normal'}
                onChange={(e) => setBrokenDraft(e.target.value === 'broken')}
                className="rounded-sm border border-hairline px-2 py-1 text-sm"
                data-testid="admin-poi-link-status"
              >
                <option value="normal">정상</option>
                <option value="broken">끊김</option>
              </select>
              <button
                type="button"
                disabled={brokenDraft === currentBroken}
                onClick={() => setShowStatusDialog(true)}
                className="rounded-sm border border-primary px-3 py-1 text-sm text-primary disabled:opacity-50"
                data-testid="admin-poi-link-status-save"
              >
                저장
              </button>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">끊김 시각</dt>
            <dd>{formatDateTime(poi.feature_link_broken_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">version</dt>
            <dd>{poi.version}</dd>
          </div>
        </dl>
      </Section>

      <Section title="일정 / 비용">
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">도착</dt>
            <dd>{formatDateTime(poi.planned_arrival_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">출발</dt>
            <dd>{formatDateTime(poi.planned_departure_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">예산</dt>
            <dd>{formatAmount(poi.budget_amount, poi.currency)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">실사용</dt>
            <dd>{formatAmount(poi.actual_amount, poi.currency)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">마커</dt>
            <dd>
              {poi.custom_marker_color ?? '—'} / {poi.custom_marker_icon ?? '—'}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">URL</dt>
            <dd className="break-all">{poi.user_url ?? '—'}</dd>
          </div>
        </dl>
        {poi.user_note && <p className="mt-4 text-sm text-ink">{poi.user_note}</p>}
      </Section>

      <Section title="Snapshot">
        <pre
          className="max-h-80 overflow-auto rounded-sm border border-hairline bg-surface-soft p-3 text-xs"
          data-testid="admin-poi-snapshot"
        >
          {JSON.stringify(poi.feature_snapshot, null, 2)}
        </pre>
      </Section>

      <Section title="최근 Audit">
        <div className="overflow-x-auto" data-testid="admin-poi-audit-list">
          <table className="min-w-full divide-y divide-hairline text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted">
                <th className="px-2 py-2">액션</th>
                <th className="px-2 py-2">사유</th>
                <th className="px-2 py-2">시각</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-hairline">
              {poi.recent_audit.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-2 py-4 text-center text-muted">
                    기록이 없습니다.
                  </td>
                </tr>
              ) : (
                poi.recent_audit.map((row) => (
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
            <h3 className="text-lg font-bold text-ink">POI 연결 상태 변경</h3>
            <p className="text-xs text-muted">
              {currentBroken ? '끊김' : '정상'} → {brokenDraft ? '끊김' : '정상'}
            </p>
            <FormTextArea
              id="admin-poi-action-reason"
              label="사유"
              hint="감사 로그에 기록됩니다."
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              data-testid="admin-poi-action-reason"
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
                onClick={onLinkStatusSave}
                className="rounded-sm bg-primary px-3 py-2 text-sm text-white disabled:opacity-50"
                data-testid="admin-poi-action-confirm"
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
