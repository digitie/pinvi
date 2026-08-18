'use client';

import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiClient, ApiError, adminApi, isRequestTimeoutError, queryKeys } from '@pinvi/api-client';
import type { KorTravelMapCurationCollectionImportResponse } from '@pinvi/schemas';
import { Download, RefreshCw } from 'lucide-react';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const inputClass = 'rounded-sm border border-hairline px-2 py-1 text-sm';
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

type PublishSelection = 'unchanged' | 'published' | 'draft';

function toPublished(selection: PublishSelection): boolean | undefined {
  if (selection === 'published') return true;
  if (selection === 'draft') return false;
  return undefined;
}

function importErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return 'canonical collection import 요청을 완료하지 못했습니다. 같은 요청을 다시 시도할 수 있습니다.';
  }
  if (error.status === 409) {
    return '원격 또는 로컬 상태가 바뀌었거나 이 Idempotency-Key가 다른 요청에 사용됐습니다. 입력을 확인한 뒤 새 요청으로 다시 실행하세요.';
  }
  if (error.status === 413) {
    return 'collection이 허용 상한 2,000개를 넘습니다. Map collection을 분리한 뒤 다시 실행하세요.';
  }
  if (error.status === 404) {
    return '공개 collection을 찾을 수 없거나 refresh 대상이 아직 없습니다.';
  }
  if (error.status === 503) {
    return 'Map snapshot service를 현재 사용할 수 없습니다. 자동 재시도하지 않았습니다.';
  }
  return error.message;
}

export function KorTravelMapCurationCollectionImportPanel() {
  const queryClient = useQueryClient();
  const [collectionId, setCollectionId] = useState('');
  const [mode, setMode] = useState<'create' | 'refresh'>('create');
  const [publishSelection, setPublishSelection] = useState<PublishSelection>('unchanged');
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [result, setResult] = useState<KorTravelMapCurationCollectionImportResponse | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const clearTerminalState = () => {
    setIdempotencyKey(null);
    setResult(null);
    setValidationError(null);
  };

  const importMutation = useMutation({
    mutationFn: ({ commandKey }: { commandKey: string }) =>
      adminApi(apiClient).importKorTravelMapCurationCollection(
        {
          collection_id: collectionId.trim(),
          mode,
          is_published: toPublished(publishSelection),
        },
        commandKey,
      ),
    onSuccess: async (nextResult) => {
      setResult(nextResult);
      setValidationError(null);
      // 성공한 command는 terminal replay가 끝났다. 같은 입력을 다시 반영하려면
      // 새 Idempotency-Key를 만들어 현재 Map snapshot을 다시 읽어야 한다.
      setIdempotencyKey(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.admin.noticePlansAll() });
    },
    onError: (nextError) => {
      // 4xx는 server가 terminal outcome으로 확정한 요청이다. 다음 submit은 반드시
      // 새 command여야 하므로 같은 key를 보존하지 않는다. 네트워크·5xx만 수동 replay를
      // 허용한다.
      // 클라이언트 시간 예산으로 끊긴 요청은 서버가 **확정하지 않은** 상태다 —
      // terminal 4xx로 오분류해 key를 버리면 재시도가 새 command가 되어 중복 import가 된다
      // (T-316 요청 수명 계약 ③).
      if (
        nextError instanceof ApiError &&
        nextError.status < 500 &&
        !isRequestTimeoutError(nextError)
      ) {
        setIdempotencyKey(null);
      }
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedCollectionId = collectionId.trim();
    if (!uuidPattern.test(normalizedCollectionId)) {
      setValidationError('Map canonical collection UUID를 정확히 입력하세요.');
      return;
    }
    setValidationError(null);
    const commandKey = idempotencyKey ?? crypto.randomUUID();
    setIdempotencyKey(commandKey);
    importMutation.mutate({ commandKey });
  };

  const resetForChangedInput = () => {
    if (idempotencyKey !== null || result !== null || importMutation.error !== null) {
      clearTerminalState();
      importMutation.reset();
    }
  };

  const error =
    validationError ?? (importMutation.error ? importErrorMessage(importMutation.error) : null);
  const canRetrySameCommand =
    idempotencyKey !== null &&
    importMutation.error !== null &&
    (!(importMutation.error instanceof ApiError) || importMutation.error.status >= 500);

  return (
    <section
      className="rounded-sm border border-hairline bg-surface-soft p-4"
      aria-labelledby="canonical-import-heading"
      data-testid="admin-notice-canonical-import"
    >
      <div className="mb-3">
        <h2 id="canonical-import-heading" className="font-semibold">
          Map canonical collection 가져오기
        </h2>
        <p className="mt-1 text-sm text-muted">
          공개된 Map collection 하나를 PinVi 추천 여행으로 반영합니다. refresh는 Map provenance가
          있는 POI만 바꾸며 수동 PO이는 유지합니다.
        </p>
      </div>

      <form className="grid gap-3 md:grid-cols-4" onSubmit={submit}>
        <label className="grid gap-1 text-sm md:col-span-2">
          <span>collection UUID</span>
          <input
            className={inputClass}
            value={collectionId}
            onChange={(event) => {
              setCollectionId(event.target.value);
              resetForChangedInput();
            }}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            inputMode="text"
            data-testid="admin-notice-canonical-import-collection-id"
          />
        </label>
        <label className="grid gap-1 text-sm">
          <span>반영 방식</span>
          <select
            className={inputClass}
            value={mode}
            onChange={(event) => {
              setMode(event.target.value as 'create' | 'refresh');
              resetForChangedInput();
            }}
            data-testid="admin-notice-canonical-import-mode"
          >
            <option value="create">새 추천 여행 만들기</option>
            <option value="refresh">기존 Map 여행 갱신</option>
          </select>
        </label>
        <label className="grid gap-1 text-sm">
          <span>공개 상태</span>
          <select
            className={inputClass}
            value={publishSelection}
            onChange={(event) => {
              setPublishSelection(event.target.value as PublishSelection);
              resetForChangedInput();
            }}
            data-testid="admin-notice-canonical-import-published"
          >
            <option value="unchanged">현재 상태 유지</option>
            <option value="published">공개</option>
            <option value="draft">초안</option>
          </select>
        </label>
        <div className="flex items-end gap-2 md:col-span-4">
          <button
            type="submit"
            disabled={importMutation.isPending}
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-cta px-3 text-sm font-semibold text-on-primary hover:bg-cta-hover disabled:opacity-60"
            data-testid="admin-notice-canonical-import-submit"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
            {importMutation.isPending ? '가져오는 중…' : '가져오기'}
          </button>
          {canRetrySameCommand && (
            <button
              type="button"
              className="inline-flex h-9 items-center gap-1 rounded-sm border border-hairline px-3 text-sm font-semibold"
              onClick={() => importMutation.mutate({ commandKey: idempotencyKey })}
              disabled={importMutation.isPending}
              data-testid="admin-notice-canonical-import-retry"
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
          data-testid="admin-notice-canonical-import-error"
        >
          {error}
        </p>
      )}

      {result && (
        <div
          className="mt-3 rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text"
          data-testid="admin-notice-canonical-import-result"
        >
          {result.not_modified
            ? 'Map snapshot이 변경되지 않아 local plan·POI는 유지했습니다.'
            : result.created_plan
              ? '새 추천 여행을 만들었습니다.'
              : '기존 Map 추천 여행을 갱신했습니다.'}{' '}
          복사 {result.copied_poi_count}개, 제거 {result.removed_poi_count}개, source revision{' '}
          {result.source_curation_collection_revision}.
        </div>
      )}
    </section>
  );
}
