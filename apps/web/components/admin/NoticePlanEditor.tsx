'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { NoticePlan, NoticePlanCreate, NoticePlanUpdate } from '@pinvi/schemas';
import { ArrowLeft, Loader2, Save, Trash2 } from 'lucide-react';
import { AdminPage } from '@/components/admin/AdminPage';
import { NoticeAttachmentPanel } from '@/components/admin/NoticeAttachmentPanel';
import { NoticePoiEditor } from '@/components/admin/NoticePoiEditor';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'mt-0.5 w-full rounded-sm border border-hairline px-2 py-1 text-sm';

type PlanDraft = {
  slug: string;
  title: string;
  category: string;
  summary: string;
  source_name: string;
  destination: string;
  starts_on: string;
  ends_on: string;
  is_published: boolean;
};

const emptyDraft: PlanDraft = {
  slug: '',
  title: '',
  category: 'recommended',
  summary: '',
  source_name: '',
  destination: '',
  starts_on: '',
  ends_on: '',
  is_published: false,
};

function draftFromPlan(plan: NoticePlan): PlanDraft {
  return {
    slug: plan.slug,
    title: plan.title,
    category: plan.category,
    summary: plan.summary ?? '',
    source_name: plan.source_name ?? '',
    destination: plan.destination ?? '',
    starts_on: plan.starts_on ?? '',
    ends_on: plan.ends_on ?? '',
    is_published: plan.is_published,
  };
}

function nullable(value: string): string | null {
  const trimmed = value.trim();
  return trimmed || null;
}

function createBody(draft: PlanDraft): NoticePlanCreate {
  return {
    slug: draft.slug.trim(),
    title: draft.title.trim(),
    category: draft.category.trim() || 'recommended',
    summary: nullable(draft.summary),
    source_name: nullable(draft.source_name),
    destination: nullable(draft.destination),
    starts_on: nullable(draft.starts_on),
    ends_on: nullable(draft.ends_on),
    is_published: draft.is_published,
  };
}

function updateBody(draft: PlanDraft): NoticePlanUpdate {
  const body = createBody(draft);
  return {
    title: body.title,
    category: body.category,
    summary: body.summary,
    source_name: body.source_name,
    destination: body.destination,
    starts_on: body.starts_on,
    ends_on: body.ends_on,
    is_published: body.is_published,
  };
}

export function NoticePlanEditor({ planId }: { planId?: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const isNew = !planId;
  const [draft, setDraft] = useState<PlanDraft>(emptyDraft);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const planQuery = useQuery({
    queryKey: planId ? queryKeys.admin.noticePlan(planId) : ['admin', 'notice-plan', 'new'],
    queryFn: () => adminApi(apiClient).getNoticePlan(planId!),
    enabled: Boolean(planId),
  });

  const plan = planQuery.data ?? null;

  useEffect(() => {
    if (plan) setDraft(draftFromPlan(plan));
  }, [plan]);

  const invalidate = async (nextPlanId?: string) => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.admin.noticePlansAll() });
    if (nextPlanId ?? planId) {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.admin.noticePlan(nextPlanId ?? planId!),
      });
    }
  };

  const saveMutation = useMutation({
    mutationFn: () =>
      isNew
        ? adminApi(apiClient).createNoticePlan(createBody(draft))
        : adminApi(apiClient).updateNoticePlan(planId!, updateBody(draft), plan?.version),
    onSuccess: async (saved) => {
      setError(null);
      setMessage('추천 여행을 저장했습니다.');
      await invalidate(saved.notice_plan_id);
      if (isNew) {
        router.replace(`/admin/notice-plans/${saved.notice_plan_id}`);
      }
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : '추천 여행을 저장하지 못했습니다.'),
  });

  const deleteMutation = useMutation({
    mutationFn: () => adminApi(apiClient).deleteNoticePlan(planId!, plan?.version),
    onSuccess: async () => {
      await invalidate();
      router.replace('/admin/notice-plans');
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : '추천 여행을 삭제하지 못했습니다.'),
  });

  const update = (patch: Partial<PlanDraft>) => setDraft((prev) => ({ ...prev, ...patch }));

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage(null);
    setError(null);
    saveMutation.mutate();
  };

  const reload = async () => {
    if (!planId) return;
    await invalidate(planId);
  };

  const busy = saveMutation.isPending || deleteMutation.isPending;

  if (!isNew && planQuery.isLoading) {
    return (
      <AdminPage title="추천 여행 편집">
        <div className="flex min-h-40 items-center justify-center text-sm text-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          불러오는 중...
        </div>
      </AdminPage>
    );
  }

  if (!isNew && planQuery.isError) {
    return (
      <AdminPage title="추천 여행 편집">
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
          {planQuery.error instanceof ApiError
            ? planQuery.error.message
            : '추천 여행을 불러오지 못했습니다.'}
        </p>
      </AdminPage>
    );
  }

  return (
    <AdminPage
      title={isNew ? '추천 여행 생성' : '추천 여행 편집'}
      description="Pinvi-native 큐레이션과 kor-travel-map import 결과를 운영자가 편집합니다."
      actions={
        <Link
          href="/admin/notice-plans"
          className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          목록
        </Link>
      }
    >
      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{message}</p>
      )}
      {error && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
          {error}
        </p>
      )}

      <form onSubmit={submit} className="space-y-4 rounded-sm border border-hairline bg-white p-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="block text-xs text-muted">
            slug
            <input
              value={draft.slug}
              onChange={(event) => update({ slug: event.target.value })}
              className={inputClass}
              disabled={!isNew}
              data-testid="admin-notice-slug"
            />
          </label>
          <label className="block text-xs text-muted">
            category
            <input
              value={draft.category}
              onChange={(event) => update({ category: event.target.value })}
              className={inputClass}
              data-testid="admin-notice-category"
            />
          </label>
          <label className="block text-xs text-muted md:col-span-2">
            제목
            <input
              value={draft.title}
              onChange={(event) => update({ title: event.target.value })}
              className={inputClass}
              data-testid="admin-notice-title"
            />
          </label>
          <label className="block text-xs text-muted md:col-span-2">
            요약
            <textarea
              value={draft.summary}
              onChange={(event) => update({ summary: event.target.value })}
              className={`${inputClass} min-h-20`}
              data-testid="admin-notice-summary"
            />
          </label>
          <label className="block text-xs text-muted">
            출처
            <input
              value={draft.source_name}
              onChange={(event) => update({ source_name: event.target.value })}
              className={inputClass}
            />
          </label>
          <label className="block text-xs text-muted">
            목적지
            <input
              value={draft.destination}
              onChange={(event) => update({ destination: event.target.value })}
              className={inputClass}
              data-testid="admin-notice-destination"
            />
          </label>
          <label className="block text-xs text-muted">
            시작일
            <input
              type="date"
              value={draft.starts_on}
              onChange={(event) => update({ starts_on: event.target.value })}
              className={inputClass}
            />
          </label>
          <label className="block text-xs text-muted">
            종료일
            <input
              type="date"
              value={draft.ends_on}
              onChange={(event) => update({ ends_on: event.target.value })}
              className={inputClass}
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={draft.is_published}
              onChange={(event) => update({ is_published: event.target.checked })}
              data-testid="admin-notice-published"
            />
            공개
          </label>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={busy}
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-ink px-3 text-sm font-semibold text-white disabled:opacity-50"
            data-testid="admin-notice-save"
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Save className="h-4 w-4" aria-hidden="true" />
            )}
            저장
          </button>
          {!isNew && (
            <button
              type="button"
              disabled={busy}
              onClick={() => deleteMutation.mutate()}
              className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold text-error-text disabled:opacity-50"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              삭제
            </button>
          )}
          {plan && <span className="self-center text-xs text-muted">version {plan.version}</span>}
        </div>
      </form>

      {plan && (
        <>
          <NoticePoiEditor plan={plan} onReload={reload} />
          <NoticeAttachmentPanel planId={plan.notice_plan_id} title="Plan 첨부" />
        </>
      )}
    </AdminPage>
  );
}
