'use client';

import { useEffect, useState } from 'react';
import { ApiError, adminApi } from '@tripmate/api-client';
import type { AdminStatsOverview } from '@tripmate/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { apiClient } from '@/lib/api';

const formatNumber = (value: number | undefined) => (value === undefined ? '—' : value.toLocaleString('ko-KR'));

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStatsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    adminApi(apiClient)
      .getStatsOverview()
      .then((result) => {
        if (cancelled) return;
        setStats(result);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : '운영 지표를 불러오지 못했습니다.');
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const cards: { label: string; value: string; hint: string }[] = [
    { label: '사용자 총 수', value: formatNumber(stats?.users_total), hint: 'deleted 제외' },
    { label: '24h 가입', value: formatNumber(stats?.users_24h), hint: '최근 24시간' },
    {
      label: '인증 대기',
      value: formatNumber(stats?.users_pending_verification),
      hint: 'pending_verification',
    },
    { label: '여행 총 수', value: formatNumber(stats?.trips_total), hint: 'deleted 제외' },
    { label: '활성 여행', value: formatNumber(stats?.trips_active), hint: 'planned / in_progress' },
    { label: 'POI 총 수', value: formatNumber(stats?.pois_total), hint: 'deleted 제외' },
    { label: '이메일 큐 대기', value: formatNumber(stats?.email_queue_pending), hint: 'pending' },
    {
      label: 'API 실패 24h',
      value: formatNumber(stats?.api_calls_failed_24h),
      hint: `${formatNumber(stats?.api_calls_24h)} calls`,
    },
  ];

  return (
    <AdminPage title="대시보드" description="TripMate app DB 기준 운영 지표">
      {error && (
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-sm border border-hairline bg-white p-4"
            data-testid={`admin-stat-${card.label}`}
          >
            <p className="text-xs uppercase tracking-wide text-muted">{card.label}</p>
            <p className="mt-2 text-2xl font-bold text-ink">
              {loading ? '...' : card.value}
            </p>
            {card.hint && <p className="mt-1 text-xs text-muted">{card.hint}</p>}
          </div>
        ))}
      </div>

      <Section title="Sprint 3 범위">
        <ul className="list-inside list-disc space-y-1 text-sm text-ink">
          <li>RBAC + audit chain ✅</li>
          <li>사용자 목록/상세, force-verify, disable ✅</li>
          <li>이메일 큐 조회/재발송 ✅</li>
          <li>감사 로그 read-only + chain 검증 ✅</li>
          <li>여행/POI/API 호출 로그/위치 감사 로그 ✅</li>
          <li>Feature / ETL / seed-reset — krtour-map 또는 운영 안전장치 후 결선</li>
        </ul>
      </Section>
    </AdminPage>
  );
}
