'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  CopyPlus,
  Loader2,
  MapPin,
  Newspaper,
  RefreshCw,
} from 'lucide-react';
import { ApiError, noticePlanApi } from '@tripmate/api-client';
import type { NoticePlan } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';
import { NoticePlanCopyDialog } from '@/components/notice-plans/NoticePlanCopyDialog';

const CATEGORY_FILTERS = [
  { value: 'all', label: '전체' },
  { value: 'recommended', label: '추천' },
  { value: 'seasonal', label: '시즌' },
  { value: 'festival', label: '축제' },
] as const;

type CategoryFilter = (typeof CATEGORY_FILTERS)[number]['value'];

function formatDate(value: string | null): string {
  if (!value) {
    return '미정';
  }
  return new Intl.DateTimeFormat('ko-KR', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(new Date(value));
}

export function NoticePlanShelf() {
  const [plans, setPlans] = useState<NoticePlan[]>([]);
  const [category, setCategory] = useState<CategoryFilter>('all');
  const [loading, setLoading] = useState(true);
  const [copyPlan, setCopyPlan] = useState<NoticePlan | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeCategory = category === 'all' ? undefined : category;
  const visiblePlans = useMemo(() => plans, [plans]);

  const loadPlans = async () => {
    setLoading(true);
    setError(null);
    try {
      const items = await noticePlanApi(apiClient).list({
        category: activeCategory,
        limit: 30,
      });
      setPlans(items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '추천 여행을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadPlans();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category]);

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 border-b border-hairline pb-5 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-normal text-primary">
            Notice Plans
          </p>
          <h1 className="mt-1 text-2xl font-bold text-ink md:text-3xl">추천 여행</h1>
        </div>
        <button
          type="button"
          onClick={() => void loadPlans()}
          className="inline-flex h-10 w-fit items-center gap-2 rounded-sm border border-hairline bg-white px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          disabled={loading}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
          )}
          새로고침
        </button>
      </header>

      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">
          {message}
        </p>
      )}
      {error && (
        <p
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="notice-plans-error"
        >
          {error}
        </p>
      )}

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="추천 여행 필터">
        {CATEGORY_FILTERS.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setCategory(item.value)}
            className={
              category === item.value
                ? 'h-10 rounded-sm bg-ink px-4 text-sm font-semibold text-white'
                : 'h-10 rounded-sm border border-hairline bg-white px-4 text-sm font-semibold text-ink hover:bg-surface-soft'
            }
            role="tab"
            aria-selected={category === item.value}
          >
            {item.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex min-h-56 items-center justify-center rounded-sm border border-hairline bg-white text-sm text-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          불러오는 중...
        </div>
      ) : visiblePlans.length === 0 ? (
        <div className="flex min-h-56 flex-col items-center justify-center rounded-sm border border-hairline bg-white px-4 text-center">
          <Newspaper className="h-8 w-8 text-muted" aria-hidden="true" />
          <p className="mt-3 text-sm font-semibold text-ink">표시할 추천 여행이 없습니다.</p>
          <p className="mt-1 text-xs text-muted">공개된 추천 여행이 생기면 이곳에 나타납니다.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="notice-plan-list">
          {visiblePlans.map((plan) => (
            <article key={plan.notice_plan_id} className="rounded-sm border border-hairline bg-white p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate text-lg font-bold text-ink">{plan.title}</h2>
                  <p className="mt-1 flex items-center gap-1 text-sm text-muted">
                    <MapPin className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="truncate">{plan.destination ?? '목적지 미정'}</span>
                  </p>
                </div>
                <span className="shrink-0 rounded-sm bg-surface-soft px-2 py-1 text-xs font-semibold text-muted">
                  {plan.category}
                </span>
              </div>
              {plan.summary && <p className="mt-3 line-clamp-3 text-sm text-body">{plan.summary}</p>}
              <div className="mt-4 flex items-center justify-between gap-3 text-sm text-muted">
                <span>
                  {formatDate(plan.starts_on)} - {formatDate(plan.ends_on)}
                </span>
                <span>{plan.source_name ?? '출처 미정'}</span>
              </div>
              <button
                type="button"
                onClick={() => setCopyPlan(plan)}
                className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-sm bg-primary px-4 text-sm font-semibold text-white"
                data-testid={`notice-plan-copy-${plan.notice_plan_id}`}
              >
                <CopyPlus className="h-4 w-4" aria-hidden="true" />
                내 여행으로 가져오기
              </button>
            </article>
          ))}
        </div>
      )}

      {copyPlan && (
        <NoticePlanCopyDialog
          plan={copyPlan}
          onClose={() => setCopyPlan(null)}
          onCopied={(result) =>
            setMessage(
              result.created_trip
                ? '추천 여행으로 새 여행을 만들었습니다.'
                : '선택한 여행에 추천 여행을 추가했습니다.'
            )
          }
        />
      )}
    </div>
  );
}
