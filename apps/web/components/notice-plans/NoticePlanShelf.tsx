'use client';

import { useEffect, useMemo, useState } from 'react';
import { CopyPlus, Loader2, MapPin, RefreshCw } from 'lucide-react';
import { ApiError, noticePlanApi } from '@pinvi/api-client';
import type { NoticePlan } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { NoticePlanCopyDialog } from '@/components/notice-plans/NoticePlanCopyDialog';
import { buttonClassName } from '@/components/ui/Button';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(app) · design-system: DESIGN.md
 * state: 로딩=카드 skeleton · 빈 상태=분류별 문구 + 회복 행동 · filter: role=group + aria-pressed + 44px(/trips와 동일 계약)
 */

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
          <h1 className="text-2xl font-bold tracking-tight text-ink md:text-3xl">추천 여행</h1>
          <p className="mt-2 text-sm text-muted">
            공공 공지·행사에서 만든 일정을 내 여행으로 복사해 쓸 수 있어요.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadPlans()}
          className="inline-flex h-10 w-fit items-center gap-2 rounded-sm border border-hairline bg-canvas px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
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
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{message}</p>
      )}
      {error && (
        <p
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          role="alert"
          data-testid="notice-plans-error"
        >
          {error}
        </p>
      )}

      {/* 패널을 바꾸는 탭이 아니라 같은 목록을 거르는 토글 — role=group + aria-pressed, 터치 타깃 44px(TripDashboard와 동일 계약). */}
      <div className="flex flex-wrap gap-2" role="group" aria-label="추천 여행 필터">
        {CATEGORY_FILTERS.map((item) => (
          <button
            key={item.value}
            type="button"
            onClick={() => setCategory(item.value)}
            className={
              category === item.value
                ? 'focus-ring inline-flex min-h-11 items-center rounded-sm bg-ink px-4 text-sm font-semibold text-canvas'
                : 'focus-ring inline-flex min-h-11 items-center rounded-sm border border-hairline bg-canvas px-4 text-sm font-semibold text-ink hover:bg-surface-soft'
            }
            aria-pressed={category === item.value}
          >
            {item.label}
          </button>
        ))}
      </div>

      {loading ? (
        // 형태가 정해진 카드 목록은 spinner 대신 skeleton(DESIGN.md 상태 UI).
        <div
          className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"
          aria-busy="true"
          aria-live="polite"
        >
          <span className="sr-only">추천 여행을 불러오는 중…</span>
          {[0, 1, 2].map((card) => (
            <div
              key={card}
              className="animate-pulse rounded-sm border border-hairline bg-canvas p-4"
            >
              <div className="h-5 w-3/5 rounded-sm bg-surface-strong" />
              <div className="mt-3 h-3 w-2/5 rounded-sm bg-surface-soft" />
              <div className="mt-4 h-3 w-full rounded-sm bg-surface-soft" />
              <div className="mt-2 h-3 w-4/5 rounded-sm bg-surface-soft" />
              <div className="mt-5 h-11 w-full rounded-sm bg-surface-soft" />
            </div>
          ))}
        </div>
      ) : visiblePlans.length === 0 ? (
        <div className="rounded-sm border border-hairline bg-canvas p-6">
          <p className="text-sm font-semibold text-ink">
            {category === 'all'
              ? '표시할 추천 여행이 없습니다.'
              : '이 분류에 해당하는 추천 여행이 없습니다.'}
          </p>
          <p className="mt-1 text-sm text-muted">
            {category === 'all'
              ? '공개된 추천 여행이 생기면 이곳에 나타납니다.'
              : '전체 분류로 돌아가면 다른 추천 여행을 볼 수 있습니다.'}
          </p>
          {category !== 'all' ? (
            <button
              type="button"
              onClick={() => setCategory('all')}
              className={buttonClassName({ variant: 'secondary', className: 'mt-4' })}
            >
              전체 보기
            </button>
          ) : null}
        </div>
      ) : (
        <div
          className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"
          data-testid="notice-plan-list"
        >
          {visiblePlans.map((plan) => (
            <article
              key={plan.notice_plan_id}
              className="rounded-sm border border-hairline bg-canvas p-4"
            >
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
              {plan.summary && (
                <p className="mt-3 line-clamp-3 text-sm text-body">{plan.summary}</p>
              )}
              <div className="mt-4 flex items-center justify-between gap-3 text-sm text-muted">
                <span>
                  {formatDate(plan.starts_on)} - {formatDate(plan.ends_on)}
                </span>
                <span>{plan.source_name ?? '출처 미정'}</span>
              </div>
              <button
                type="button"
                onClick={() => setCopyPlan(plan)}
                className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-sm bg-cta px-4 text-sm font-semibold text-on-primary hover:bg-cta-hover"
                data-testid={`notice-plan-copy-${plan.notice_plan_id}`}
              >
                <CopyPlus className="h-4 w-4" aria-hidden="true" />내 여행으로 가져오기
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
                : '선택한 여행에 추천 여행을 추가했습니다.',
            )
          }
          onCopyUncertain={() => {
            // 취소해도 서버가 복사를 끝냈을 수 있다 — 결과를 단정하지 않고 확인을 요청한다.
            setMessage(
              '복사 요청을 취소했습니다. 서버에 이미 접수됐을 수 있으니 여행 목록에서 확인해 주세요.',
            );
          }}
        />
      )}
    </div>
  );
}
