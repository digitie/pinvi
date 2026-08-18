'use client';

import { useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, queryKeys } from '@pinvi/api-client';
import type { KorTravelMapCurationCutoverBackfillResponse } from '@pinvi/schemas';
import { RefreshCw, ShieldCheck } from 'lucide-react';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const preflightQueryKey = [
  'admin',
  'notice-plans',
  'curation-cutover',
  'legacy-preflight',
] as const;

function backfillErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'canonical cutover backfill 요청을 완료하지 못했습니다. 네트워크 또는 5xx 뒤에만 같은 요청을 다시 시도할 수 있습니다.';
  }
  if (error.status === 409) {
    return 'sealed mapping 또는 legacy provenance가 바뀌었습니다. 아래 사전 점검을 다시 실행한 뒤 새 요청으로 확인하세요.';
  }
  if (error.status === 413) {
    return 'canonical collection이 허용 상한 2,000개를 넘습니다. Map collection을 분리한 뒤 다시 점검하세요.';
  }
  if (error.status === 404) {
    return 'active legacy Map plan 또는 sealed canonical collection을 찾을 수 없습니다.';
  }
  if (error.status === 502) {
    return 'Map snapshot 계약이 현재 PinVi 계약과 다릅니다. 배포 receipt를 확인하세요.';
  }
  if (error.status === 503) {
    return 'Map snapshot service를 현재 사용할 수 없습니다. 자동 재시도하지 않았습니다.';
  }
  return error.message;
}

export function KorTravelMapCurationCutoverBackfillPanel() {
  const queryClient = useQueryClient();
  const [noticePlanId, setNoticePlanId] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [result, setResult] = useState<KorTravelMapCurationCutoverBackfillResponse | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const preflightQuery = useQuery({
    queryKey: preflightQueryKey,
    queryFn: () => adminApi(apiClient).getKorTravelMapCurationCutoverLegacyPreflight(),
  });
  const backfillMutation = useMutation({
    mutationFn: ({ commandKey }: { commandKey: string }) =>
      adminApi(apiClient).backfillKorTravelMapCurationCutover(
        { notice_plan_id: noticePlanId.trim() },
        commandKey,
      ),
    onSuccess: async (nextResult) => {
      setResult(nextResult);
      setValidationError(null);
      // terminal backfill은 replay가 끝났다. 다음 explicit backfill은 현재 sealed state를
      // 다시 읽는 별도의 command여야 한다.
      setIdempotencyKey(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.admin.noticePlansAll() }),
        queryClient.invalidateQueries({ queryKey: preflightQueryKey }),
      ]);
    },
    onError: (nextError) => {
      // server가 확정한 4xx는 같은 command를 되살리지 않는다. transport/5xx만
      // operation replay 목적으로 동일 key의 명시적 retry를 허용한다.
      if (nextError instanceof ApiError && nextError.status < 500) {
        setIdempotencyKey(null);
      }
    },
  });

  const resetForChangedInput = () => {
    if (idempotencyKey !== null || result !== null || backfillMutation.error !== null) {
      setIdempotencyKey(null);
      setResult(null);
      setValidationError(null);
      backfillMutation.reset();
    }
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedPlanId = noticePlanId.trim();
    if (!uuidPattern.test(normalizedPlanId)) {
      setValidationError('legacy Map notice plan UUID를 정확히 입력하세요.');
      return;
    }
    if (preflightQuery.data?.ready !== true) {
      setValidationError(
        '사전 점검이 ready가 아닙니다. 모든 provenance issue를 해소한 뒤 다시 점검하세요.',
      );
      return;
    }
    setValidationError(null);
    const commandKey = idempotencyKey ?? crypto.randomUUID();
    setIdempotencyKey(commandKey);
    backfillMutation.mutate({ commandKey });
  };

  const error =
    validationError ??
    (backfillMutation.error ? backfillErrorMessage(backfillMutation.error) : null);
  const canRetrySameCommand =
    idempotencyKey !== null &&
    backfillMutation.error !== null &&
    (!(backfillMutation.error instanceof ApiError) || backfillMutation.error.status >= 500);
  const preflight = preflightQuery.data;
  const ready = preflight?.ready === true;

  return (
    <section
      className="rounded-sm border border-hairline bg-surface-soft p-4"
      aria-labelledby="cutover-backfill-heading"
      data-testid="admin-notice-cutover-backfill"
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="cutover-backfill-heading" className="font-semibold">
            Legacy Map 추천 여행 canonical backfill
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            sealed mapping이 정한 canonical collection으로 legacy source POI만 교체합니다. 수동
            PO이는 보존하며, 서버가 plan identity와 mapping을 다시 검증합니다.
          </p>
        </div>
        <button
          type="button"
          className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold"
          onClick={() => void preflightQuery.refetch()}
          disabled={preflightQuery.isFetching}
          data-testid="admin-notice-cutover-preflight-refresh"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {preflightQuery.isFetching ? '점검 중…' : '사전 점검 다시 실행'}
        </button>
      </div>

      {preflightQuery.isError && (
        <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
          사전 점검을 읽지 못했습니다. canonical backfill은 시작하지 않았습니다.
        </p>
      )}
      {preflight && (
        <div
          className={`mb-3 rounded-sm px-3 py-2 text-sm ${
            ready ? 'bg-success-bg text-success-text' : 'bg-error-bg text-error-text'
          }`}
          data-testid="admin-notice-cutover-preflight-result"
        >
          <p className="inline-flex items-center gap-1 font-semibold">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {ready
              ? 'sealed mapping과 legacy provenance가 backfill 준비 상태입니다.'
              : 'backfill이 차단돼 있습니다.'}
          </p>
          <p className="mt-1">
            legacy plan {preflight.legacy_plan_count}개, source POI{' '}
            {preflight.legacy_source_poi_count}개, manual POI {preflight.manual_poi_count}개,
            backfillable plan {preflight.backfillable_plan_count}개.
          </p>
          {!ready && preflight.issues.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {preflight.issues.slice(0, 5).map((issue) => (
                <li
                  key={`${issue.code}:${issue.notice_plan_id ?? ''}:${issue.notice_poi_id ?? ''}`}
                >
                  {issue.code}: {issue.detail}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <form className="grid gap-3 md:grid-cols-3" onSubmit={submit}>
        <label className="grid gap-1 text-sm md:col-span-2">
          <span>legacy notice plan UUID</span>
          <input
            className={inputClass}
            value={noticePlanId}
            onChange={(event) => {
              setNoticePlanId(event.target.value);
              resetForChangedInput();
            }}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            inputMode="text"
            data-testid="admin-notice-cutover-backfill-plan-id"
          />
        </label>
        <div className="flex items-end gap-2">
          <button
            type="submit"
            disabled={backfillMutation.isPending || !ready}
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-cta px-3 text-sm font-semibold text-on-primary hover:bg-cta-hover disabled:opacity-60"
            data-testid="admin-notice-cutover-backfill-submit"
          >
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {backfillMutation.isPending ? '전환 중…' : 'canonical backfill'}
          </button>
          {canRetrySameCommand && (
            <button
              type="button"
              className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold"
              onClick={() => backfillMutation.mutate({ commandKey: idempotencyKey })}
              disabled={backfillMutation.isPending}
              data-testid="admin-notice-cutover-backfill-retry"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              같은 요청 재시도
            </button>
          )}
        </div>
      </form>

      {error && (
        <p
          role="alert"
          className="mt-3 rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="admin-notice-cutover-backfill-error"
        >
          {error}
        </p>
      )}
      {result && (
        <p
          className="mt-3 rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text"
          data-testid="admin-notice-cutover-backfill-result"
        >
          {result.replayed
            ? '이미 완료된 canonical backfill 결과를 replay했습니다.'
            : 'canonical backfill을 완료했습니다.'}{' '}
          복사 {result.import_result.copied_poi_count}개, 제거{' '}
          {result.import_result.removed_poi_count}개, source revision{' '}
          {result.import_result.source_curation_collection_revision}.
        </p>
      )}
    </section>
  );
}
