'use client';

import { useEffect, useState } from 'react';
import { ApiError, adminApi } from '@pinvi/api-client';
import type {
  AdminStatsOverview,
  AdminSystemServiceStatus,
  AdminSystemSummary,
} from '@pinvi/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { apiClient } from '@/lib/api';

const formatNumber = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : value.toLocaleString('ko-KR');
const formatLatency = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : `${value} ms`;
const formatPercent = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : `${value.toFixed(1)}%`;
const formatLoad = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : value.toFixed(2);
const formatBytes = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[unit]}`;
};
const formatDateTime = (value: string | undefined) =>
  value
    ? new Intl.DateTimeFormat('ko-KR', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      }).format(new Date(value))
    : '—';
const ratioPercent = (used: number | null | undefined, total: number | null | undefined) => {
  if (!used || !total || total <= 0) return 0;
  return Math.min(100, Math.round((used / total) * 100));
};

const statusMeta: Record<
  AdminSystemServiceStatus['status'],
  { label: string; className: string; dotClassName: string }
> = {
  ok: {
    label: '정상',
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800',
    dotClassName: 'bg-emerald-500',
  },
  degraded: {
    label: '주의',
    className: 'border-amber-200 bg-amber-50 text-amber-800',
    dotClassName: 'bg-amber-500',
  },
  down: {
    label: '중단',
    className: 'border-red-200 bg-red-50 text-red-800',
    dotClassName: 'bg-red-500',
  },
  unknown: {
    label: '미확인',
    className: 'border-hairline bg-surface-soft text-muted',
    dotClassName: 'bg-muted',
  },
};

const systemPlaceholders: AdminSystemServiceStatus[] = [
  { key: 'pinvi_api', label: 'Pinvi API', status: 'unknown', message: '확인 중', latency_ms: null },
  { key: 'postgres', label: 'DB', status: 'unknown', message: '확인 중', latency_ms: null },
  { key: 'pinvi_web', label: 'Web', status: 'unknown', message: '확인 중', latency_ms: null },
  { key: 'dagster', label: 'Dagster', status: 'unknown', message: '확인 중', latency_ms: null },
  {
    key: 'kor_travel_map_api',
    label: 'kor-travel-map API',
    status: 'unknown',
    message: '확인 중',
    latency_ms: null,
  },
  { key: 'rustfs', label: 'RustFS', status: 'unknown', message: '확인 중', latency_ms: null },
];

function BarSeries({
  title,
  values,
  tone,
  testId,
}: {
  title: string;
  values: { label: string; primary: number; secondary?: number }[];
  tone: 'blue' | 'green';
  testId: string;
}) {
  const max = Math.max(1, ...values.map((value) => Math.max(value.primary, value.secondary ?? 0)));
  const primaryClass = tone === 'blue' ? 'bg-info-text' : 'bg-emerald-600';
  const secondaryClass = tone === 'blue' ? 'bg-error-text' : 'bg-amber-500';
  return (
    <div className="rounded-sm border border-hairline bg-white p-4" data-testid={testId}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="text-xs text-muted">최근 24시간</p>
      </div>
      <div className="mt-4 flex h-36 items-end gap-1" aria-hidden="true">
        {values.map((value) => (
          <div key={value.label} className="flex min-w-0 flex-1 items-end gap-px">
            <div
              className={`w-full rounded-t-sm ${primaryClass}`}
              style={{ height: `${Math.max(4, (value.primary / max) * 100)}%` }}
              title={`${value.label}: ${value.primary.toLocaleString('ko-KR')}`}
            />
            {value.secondary !== undefined && (
              <div
                className={`w-full rounded-t-sm ${secondaryClass}`}
                style={{ height: `${Math.max(4, (value.secondary / max) * 100)}%` }}
                title={`${value.label}: ${value.secondary.toLocaleString('ko-KR')}`}
              />
            )}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center justify-between text-xs text-muted">
        <span>{values[0]?.label ?? '—'}</span>
        <span>{values[values.length - 1]?.label ?? '—'}</span>
      </div>
    </div>
  );
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStatsOverview | null>(null);
  const [systemSummary, setSystemSummary] = useState<AdminSystemSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const admin = adminApi(apiClient);
    Promise.all([admin.getStatsOverview(), admin.getSystemSummary()])
      .then(([statsResult, systemResult]) => {
        if (cancelled) return;
        setStats(statsResult);
        setSystemSummary(systemResult);
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
      hint: `${formatNumber(stats?.api_calls_24h)} calls / ${formatPercent(
        stats?.api_failure_rate_pct,
      )}`,
    },
    {
      label: 'API P95',
      value: formatLatency(stats?.api_latency_p95_ms),
      hint: '최근 24시간',
    },
  ];
  const series = stats?.series_24h ?? [];
  const seriesLabels = series.map((bucket) => ({
    label: new Intl.DateTimeFormat('ko-KR', { hour: '2-digit' }).format(
      new Date(bucket.bucket_start),
    ),
    primary: bucket.api_calls,
    secondary: bucket.api_failures,
  }));
  const growthLabels = series.map((bucket) => ({
    label: new Intl.DateTimeFormat('ko-KR', { hour: '2-digit' }).format(
      new Date(bucket.bucket_start),
    ),
    primary: bucket.users_created,
    secondary: bucket.trips_created,
  }));
  const diskUsagePct = ratioPercent(
    stats?.capacity.disk_used_bytes,
    stats?.capacity.disk_total_bytes,
  );
  const attachmentQuotaPct = ratioPercent(
    stats?.capacity.attachments_total_bytes,
    stats?.capacity.user_attachment_quota_bytes,
  );

  return (
    <AdminPage title="대시보드" description="Pinvi app DB 기준 운영 지표">
      {error && <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>}

      <Section title="시스템 상태">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(systemSummary?.services ?? systemPlaceholders).map((service) => {
            const meta = statusMeta[service.status];
            return (
              <div
                key={service.key}
                className="rounded-sm border border-hairline bg-white p-4"
                data-testid={`admin-system-${service.key}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-ink">{service.label}</p>
                    <p className="mt-1 text-xs text-muted">{service.message ?? '상태 정보 없음'}</p>
                  </div>
                  <span
                    className={`inline-flex shrink-0 items-center gap-1 rounded-sm border px-2 py-1 text-xs font-semibold ${meta.className}`}
                  >
                    <span className={`h-2 w-2 rounded-full ${meta.dotClassName}`} />
                    {loading && service.status === 'unknown' ? '확인 중' : meta.label}
                  </span>
                </div>
                <p className="mt-3 text-xs text-muted">
                  latency {formatLatency(service.latency_ms)}
                </p>
              </div>
            );
          })}
        </div>
      </Section>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-sm border border-hairline bg-white p-4"
            data-testid={`admin-stat-${card.label}`}
          >
            <p className="text-xs uppercase tracking-wide text-muted">{card.label}</p>
            <p className="mt-2 text-2xl font-bold text-ink">{loading ? '...' : card.value}</p>
            {card.hint && <p className="mt-1 text-xs text-muted">{card.hint}</p>}
          </div>
        ))}
      </div>

      <Section title="운영 그래프">
        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
          <BarSeries
            title="API 호출 / 실패"
            values={seriesLabels}
            tone="blue"
            testId="admin-dashboard-series-api"
          />
          <BarSeries
            title="가입 / 여행 생성"
            values={growthLabels}
            tone="green"
            testId="admin-dashboard-series-growth"
          />
        </div>
      </Section>

      <Section title="부하와 용량">
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
          <div
            className="rounded-sm border border-hairline bg-white p-4"
            data-testid="admin-dashboard-load"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-ink">서버 부하</p>
              <p className="text-xs text-muted">CPU {formatNumber(stats?.load.cpu_count)}</p>
            </div>
            <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <div>
                <dt className="text-xs text-muted">1m</dt>
                <dd className="mt-1 font-semibold text-ink">{formatLoad(stats?.load.load_1m)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">5m</dt>
                <dd className="mt-1 font-semibold text-ink">{formatLoad(stats?.load.load_5m)}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">15m</dt>
                <dd className="mt-1 font-semibold text-ink">{formatLoad(stats?.load.load_15m)}</dd>
              </div>
            </dl>
          </div>
          <div
            className="rounded-sm border border-hairline bg-white p-4"
            data-testid="admin-dashboard-capacity-disk"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-ink">디스크</p>
              <p className="text-xs text-muted">{formatPercent(diskUsagePct)}</p>
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-sm bg-surface-soft">
              <div className="h-full bg-info-text" style={{ width: `${diskUsagePct}%` }} />
            </div>
            <p className="mt-3 text-xs text-muted">
              {formatBytes(stats?.capacity.disk_used_bytes)} /{' '}
              {formatBytes(stats?.capacity.disk_total_bytes)}
            </p>
          </div>
          <div
            className="rounded-sm border border-hairline bg-white p-4"
            data-testid="admin-dashboard-capacity"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-ink">첨부 저장소</p>
              <p className="text-xs text-muted">
                {formatNumber(stats?.capacity.attachments_count)} files
              </p>
            </div>
            <div className="mt-4 h-2 overflow-hidden rounded-sm bg-surface-soft">
              <div className="h-full bg-emerald-600" style={{ width: `${attachmentQuotaPct}%` }} />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-muted">
              <div>
                <dt>사용량</dt>
                <dd className="mt-1 font-semibold text-ink">
                  {formatBytes(stats?.capacity.attachments_total_bytes)}
                </dd>
              </div>
              <div>
                <dt>사용자 기본 한도</dt>
                <dd className="mt-1 font-semibold text-ink">
                  {formatBytes(stats?.capacity.user_attachment_quota_bytes)}
                </dd>
              </div>
              <div>
                <dt>개별 한도</dt>
                <dd className="mt-1 font-semibold text-ink">
                  {formatNumber(stats?.capacity.users_with_quota_override)}
                </dd>
              </div>
              <div>
                <dt>최대 업로드</dt>
                <dd className="mt-1 font-semibold text-ink">
                  {formatBytes(stats?.capacity.attachment_max_upload_bytes)}
                </dd>
              </div>
            </dl>
          </div>
        </div>
        <p className="mt-2 text-xs text-muted">갱신 시각 {formatDateTime(stats?.generated_at)}</p>
      </Section>

      <Section title="Admin 보강 Task">
        <ul className="list-inside list-disc space-y-1 text-sm text-ink">
          <li>T-208 Admin IA, placeholder, 시스템 상태 보드.</li>
          <li>T-209 Feature 검색·상세·source/override read-only.</li>
          <li>T-210 Feature 변경 요청 승인·반려, audit/idempotency/kill-switch.</li>
          <li>T-211 ETL/provider sync 운영 화면과 Dagster 연결.</li>
          <li>T-212 Dedup review, integrity, debug logs.</li>
          <li>T-213 카테고리 매핑, T-214 dev-only seed/reset, T-215 N150 배치 검증.</li>
        </ul>
      </Section>
    </AdminPage>
  );
}
