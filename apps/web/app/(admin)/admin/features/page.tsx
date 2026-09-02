'use client';
// T-356 2단계 파일럿 — 이 화면의 **필터 툴바와 페이저**를 KTM admin idiom으로 전환했다.
// (KTM `src/components/filter-bar.tsx` / `src/components/pagination-bar.tsx` 이식본 소비처)
//
// 원문(= 전환 전 pinvi 코드)에서 바꾼 부분과 이유:
//  1) `@/components/admin/AdminPage`의 `FilterBar`(카드 프레임 + `items-center`) →
//     `@/components/admin/filter-bar`의 `FilterBar`/`FilterField`/`FilterActions`.
//     같은 이름의 다른 컴포넌트라 import 출처만 바꿨다. 나머지 22개 admin 페이지는
//     아직 AdminPage 쪽 `FilterBar`를 쓰므로 그 export는 건드리지 않았다.
//  2) 모든 필터에 **가시 라벨**을 붙였다(M26). 전환 전에는 placeholder(`provider_dataset_id`,
//     `category`)와 `aria-label`이 라벨을 대신했다 — placeholder는 입력이 들어가는 순간 사라져
//     "이 칸이 무엇이었는지"가 없어진다. 라벨이 접근성 이름을 갖게 됐으므로 중복이 되는
//     `aria-label`(`provider dataset id`, `lifecycle_state 필터`, `publication_state 필터`,
//     `quality_state 필터`)은 제거했다 — 저장소 전체에서 이 문자열을 잡는 e2e/단위 테스트는 없다.
//  3) 지금까지 코드에만 있던 두 규칙을 `FilterField hint`로 화면에 꺼냈다:
//     provider_dataset_id는 정수 1 이상만 전송하고(그 외는 조용히 버려졌다),
//     category는 쉼표 CSV로 여러 개를 보낸다. 동작은 그대로고 설명만 보이게 됐다.
//  4) 수제 input/select/button className(`inputClass`, `rounded-sm border border-hairline …`) →
//     `@/components/admin/ui/{input,native-select,native-select-option,button}`.
//     폭은 런타임 값이 아니라 정적 클래스(`w-56`/`w-36`)이므로 FilterField에 그대로 얹었다.
//  5) 수제 이전/다음 페이저 → `CursorPager`. 경계(첫 페이지)는 native disabled 그대로,
//     전환 중에는 `Button loading`(aria-busy + spinner, 포커스 유지)으로 바뀐다.
//     `data-testid="admin-features-first" / "admin-features-next"`는 CursorPager에 부착점이
//     없어 사라졌다 — 저장소 어디에서도 참조하지 않는 것을 확인하고 뺐다(대신 pager 버튼은
//     `aria-label="첫 페이지" / "다음 페이지"`로 잡을 수 있다).
//  6) 갱신 버튼은 `disabled={isFetching}` → `loading={isFetching}`. 눌림 방지는 동일하고
//     (Button이 활성화를 막는다) 방금 누른 버튼이 탭 순서에서 빠지지 않는다.
//  7) (T-356 배선 단계) `StateAxes`의 3축이 **raw enum 문자열**(`active`/`published`/`valid` …)을
//     그대로 찍고 있었다 → KTM `status-badge.tsx` 이식본 + `lib/admin/status-label.ts` 톤/라벨
//     테이블로 교체했다. status-label은 "enum 값은 raw로 렌더하지 않는다"가 규약이고, 3축
//     6개 값(active·retired / draft·published·suppressed / valid·quarantined)이 전부 그
//     테이블에 이미 있어 라벨을 새로 지어낼 필요가 없었다. `title={축 이름}`은 그대로 남겨
//     "어느 축의 값인가"를 계속 hover로 확인할 수 있게 했다(색만으로 축을 구분하지 않는다).
//     `data-testid="admin-features-state-axes"`와 3개 span의 순서는 유지했다.
//  8) 수제 `JsonBlock`(`<pre className="max-h-52 … bg-surface-soft">`) → KTM `json-viewer.tsx`
//     이식본(`JsonViewer maxHeight="md"`). 그룹 안 JSON 렌더러를 하나로 모은다(M42).
//     `max-h-52`(13rem)는 JsonViewer의 3단 스케일(sm 10rem / md 18rem / lg 32rem)에 없어
//     한 단 위인 `md`로 올렸다 — 런타임 값으로 `max-h-[…]`를 조립하지 않는다는 규칙 때문에
//     중간값을 새로 만들지 않았다.
//
// 보존한 것(계약): 모든 `data-testid`(위 5의 두 개 제외), 쿼리 파라미터 조립(`params`),
// 필터 적용 시점(텍스트 3종은 제출, select는 즉시), 커서 스택 동작, 한국어 문구(`조회`/`갱신`/
// `첫 페이지`/`다음`), option 텍스트·value, 로컬 `formatDateTime`(ko-KR `toLocaleString` —
// `@/lib/admin/format`의 것으로 바꾸면 표시 포맷이 달라진다).

import Link from 'next/link';
import { useMemo, useState, type FormEvent } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import {
  ApiClient,
  ApiError,
  adminApi,
  queryKeys,
  type AdminFeatureListParams,
} from '@pinvi/api-client';
import type {
  AdminFeatureDetail,
  AdminFeatureLifecycleState,
  AdminFeaturePublicationState,
  AdminFeatureQualityState,
  AdminFeatureSort,
  AdminFeatureSortOrder,
  AdminFeatureSummary,
} from '@pinvi/schemas';
import { Eye, RefreshCw, Search } from 'lucide-react';
import { AdminPage } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FilterActions, FilterBar, FilterField } from '@/components/admin/filter-bar';
import { CursorPager } from '@/components/admin/pagination-bar';
import { Button } from '@/components/admin/ui/button';
import { Input } from '@/components/admin/ui/input';
import { NativeSelect } from '@/components/admin/ui/native-select';
import { NativeSelectOption } from '@/components/admin/ui/native-select-option';
import { JsonViewer } from '@/components/admin/json-viewer';
import { StatusBadge } from '@/components/admin/status-badge';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

const FEATURE_KINDS = ['place', 'event', 'notice', 'price', 'weather', 'route', 'area'] as const;
/**
 * kor-travel-map 3축 feature state (Map `1f2bdc3a` cutover). 합성 `status` 하나로
 * 뭉개면 "published 인데 quarantined" 같은 조합이 화면에서 사라지므로 축을 셋 다 노출한다.
 */
const LIFECYCLE_STATES: readonly AdminFeatureLifecycleState[] = ['active', 'retired'];
const PUBLICATION_STATES: readonly AdminFeaturePublicationState[] = [
  'draft',
  'published',
  'suppressed',
];
const QUALITY_STATES: readonly AdminFeatureQualityState[] = ['valid', 'quarantined'];
const ISSUE_FILTERS = [
  { value: 'all', label: '이슈 전체' },
  { value: 'yes', label: '이슈 있음' },
  { value: 'no', label: '이슈 없음' },
] as const;
const SORT_OPTIONS: AdminFeatureSort[] = [
  'name',
  'updated_at',
  'created_at',
  'kind',
  'provider',
  'issue_count',
];

/**
 * 표 헤더가 넘겨주는 정렬 키가 API가 아는 값인지 확인한다.
 *
 * `AdminTable`의 `serverSort.onChange`는 `column.sortKey ?? column.key`(그냥 string)를 준다 —
 * 컬럼에 `sortable`을 붙이면서 서버가 모르는 키를 쓰면 그 값이 그대로 쿼리에 실린다.
 * 캐스트로 눌러 두면 그 순간이 조용히 지나가므로 여기서 걸러낸다.
 */
function isFeatureSort(value: string): value is AdminFeatureSort {
  return (SORT_OPTIONS as string[]).includes(value);
}
const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, 500] as const;

type KindFilter = (typeof FEATURE_KINDS)[number] | 'all';
type LifecycleFilter = AdminFeatureLifecycleState | 'all';
type PublicationFilter = AdminFeaturePublicationState | 'all';
type QualityFilter = AdminFeatureQualityState | 'all';
type IssueFilter = (typeof ISSUE_FILTERS)[number]['value'];

function valuesFromCsv(value: string): string[] | undefined {
  const values = value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
  return values.length > 0 ? values : undefined;
}

function formatDateTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

function coordLabel(feature: Pick<AdminFeatureSummary, 'lon' | 'lat'>) {
  return typeof feature.lon === 'number' && typeof feature.lat === 'number'
    ? `${feature.lon.toFixed(5)}, ${feature.lat.toFixed(5)}`
    : '—';
}

/**
 * 3축을 한 줄로 붙여 표시(합성 status를 만들지 않는다 — 축 값은 그대로 보인다).
 * 라벨/톤은 `lib/admin/status-label.ts` 한 곳에서 읽는다: active 활성(success) ·
 * retired 종료(neutral) · draft 초안(info) · published 공개(success) · suppressed 비공개(neutral) ·
 * valid 유효(info) · quarantined 격리(warning). `title`은 어느 축의 값인지를 남긴다.
 */
function StateAxes({
  feature,
}: {
  feature: Pick<AdminFeatureSummary, 'lifecycle_state' | 'publication_state' | 'quality_state'>;
}) {
  return (
    <div className="flex flex-wrap gap-1" data-testid="admin-features-state-axes">
      <StatusBadge status={feature.lifecycle_state} title="lifecycle_state" />
      <StatusBadge status={feature.publication_state} title="publication_state" />
      <StatusBadge status={feature.quality_state} title="quality_state" />
    </div>
  );
}

function featureTabHref(featureId: string, tab: 'sources' | 'overrides' | 'weather-values') {
  return `/admin/features/${encodeURIComponent(featureId)}/${tab}`;
}

function JsonBlock({ value }: { value: unknown }) {
  return <JsonViewer value={value} maxHeight="md" />;
}

function CountLine({ detail }: { detail: AdminFeatureDetail }) {
  return (
    <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
      <span className="rounded-sm bg-surface-soft px-2 py-1">sources {detail.sources.length}</span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">issues {detail.issues.length}</span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">
        overrides {detail.overrides.length}
      </span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">
        transitions {detail.state_transitions.length}
      </span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">files {detail.files.length}</span>
      <span className="rounded-sm bg-surface-soft px-2 py-1">
        curations {detail.curations.length}
      </span>
    </div>
  );
}

function DetailInspector({ featureId }: { featureId: string | null }) {
  const detailQuery = useQuery({
    queryKey: featureId ? queryKeys.admin.feature(featureId) : ['admin', 'feature', null],
    queryFn: () => adminApi(apiClient).getFeature(featureId as string),
    enabled: Boolean(featureId),
  });

  if (!featureId) {
    return (
      <section
        className="rounded-sm border border-hairline bg-canvas p-4 text-sm text-muted"
        data-testid="admin-features-detail-empty"
      >
        목록에서 feature를 선택하면 상세 정보가 표시됩니다.
      </section>
    );
  }

  const detail = detailQuery.data ?? null;
  const error = detailQuery.isError
    ? detailQuery.error instanceof ApiError
      ? detailQuery.error.message
      : '상세 조회 실패'
    : null;

  return (
    <section
      className="space-y-4 rounded-sm border border-hairline bg-canvas p-4"
      data-testid="admin-features-detail"
    >
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-ink">
            {detail?.feature.name ?? 'Feature detail'}
          </h2>
          <p className="break-all font-mono text-xs text-muted">{featureId}</p>
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={() => void detailQuery.refetch()}
          data-testid="admin-features-detail-refresh"
        >
          <RefreshCw aria-hidden="true" />
          갱신
        </Button>
      </header>

      {detailQuery.isLoading && <p className="text-sm text-muted">불러오는 중…</p>}
      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-features-detail-error"
        >
          {error}
        </p>
      )}

      {detail && (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm">
            <dt className="text-muted">kind</dt>
            <dd>{detail.feature.kind}</dd>
            <dt className="text-muted">state</dt>
            <dd className="text-xs">
              <StateAxes feature={detail.feature} />
            </dd>
            <dt className="text-muted">category</dt>
            <dd>{detail.feature.category}</dd>
            <dt className="text-muted">coord</dt>
            <dd className="font-mono">{coordLabel(detail.feature)}</dd>
            <dt className="text-muted">region</dt>
            <dd>
              {detail.feature.sido_code ?? '—'} / {detail.feature.sigungu_code ?? '—'} /{' '}
              {detail.feature.legal_dong_code ?? '—'}
            </dd>
            <dt className="text-muted">marker</dt>
            <dd>
              {detail.feature.marker_color ?? '—'} / {detail.feature.marker_icon ?? '—'}
            </dd>
            <dt className="text-muted">updated</dt>
            <dd>{formatDateTime(detail.feature.updated_at)}</dd>
          </dl>

          <CountLine detail={detail} />

          <nav className="flex flex-wrap gap-2 text-xs" aria-label="feature detail tabs">
            <Link
              href={featureTabHref(detail.feature.feature_id, 'sources')}
              className="rounded-sm border border-hairline px-2 py-1"
              data-testid="admin-features-link-sources"
            >
              sources
            </Link>
            <Link
              href={featureTabHref(detail.feature.feature_id, 'overrides')}
              className="rounded-sm border border-hairline px-2 py-1"
              data-testid="admin-features-link-overrides"
            >
              overrides
            </Link>
            <Link
              href={featureTabHref(detail.feature.feature_id, 'weather-values')}
              className="rounded-sm border border-hairline px-2 py-1"
              data-testid="admin-features-link-weather-values"
            >
              weather values
            </Link>
          </nav>

          <div className="space-y-2 text-sm">
            <details open>
              <summary className="cursor-pointer font-medium">sources</summary>
              <ul className="mt-2 space-y-1 text-xs">
                {detail.sources.slice(0, 6).map((source) => (
                  <li
                    key={source.source_record_key}
                    className="break-all rounded-sm bg-surface-soft p-2"
                  >
                    {source.provider} / {source.dataset_key} / {source.source_role} /{' '}
                    {source.confidence}
                  </li>
                ))}
                {detail.sources.length === 0 && <li className="text-muted">—</li>}
              </ul>
            </details>
            <details>
              <summary className="cursor-pointer font-medium">issues</summary>
              <ul className="mt-2 space-y-1 text-xs">
                {detail.issues.slice(0, 6).map((issue) => (
                  <li key={issue.issue_id} className="rounded-sm bg-surface-soft p-2">
                    {issue.severity} / {issue.violation_type} / {issue.status}: {issue.message}
                  </li>
                ))}
                {detail.issues.length === 0 && <li className="text-muted">—</li>}
              </ul>
            </details>
            <details>
              <summary className="cursor-pointer font-medium">address</summary>
              <JsonBlock value={detail.feature.address} />
            </details>
            <details>
              <summary className="cursor-pointer font-medium">detail</summary>
              <JsonBlock value={detail.feature.detail} />
            </details>
            <details>
              <summary className="cursor-pointer font-medium">urls / raw_refs</summary>
              <JsonBlock value={{ urls: detail.feature.urls, raw_refs: detail.feature.raw_refs }} />
            </details>
          </div>
        </>
      )}
    </section>
  );
}

export default function AdminFeaturesPage() {
  const [queryInput, setQueryInput] = useState('');
  const [providerDatasetInput, setProviderDatasetInput] = useState('');
  const [categoryInput, setCategoryInput] = useState('');
  const [submitted, setSubmitted] = useState({
    q: '',
    providerDatasetId: undefined as number | undefined,
    categories: undefined as string[] | undefined,
  });
  const [kind, setKind] = useState<KindFilter>('all');
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>('active');
  const [publication, setPublication] = useState<PublicationFilter>('all');
  const [quality, setQuality] = useState<QualityFilter>('all');
  const [issue, setIssue] = useState<IssueFilter>('all');
  const [sort, setSort] = useState<AdminFeatureSort>('name');
  const [order, setOrder] = useState<AdminFeatureSortOrder>('asc');
  const [pageSize, setPageSize] = useState<(typeof PAGE_SIZE_OPTIONS)[number]>(50);
  const [cursorStack, setCursorStack] = useState<string[]>([]);
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null);

  const cursor = cursorStack.length > 0 ? cursorStack[cursorStack.length - 1] : undefined;
  const pageIndex = cursorStack.length + 1;

  const resetCursor = () => {
    setCursorStack([]);
    setSelectedFeatureId(null);
  };

  const params = useMemo<AdminFeatureListParams>(
    () => ({
      q: submitted.q || undefined,
      kind: kind === 'all' ? undefined : [kind],
      category: submitted.categories,
      // '전체'는 필터를 아예 보내지 않는다(모든 값을 나열해 보내면 Map이 새 축 값을
      // 추가했을 때 조용히 잘려 나간다).
      lifecycleState: lifecycle === 'all' ? undefined : [lifecycle],
      publicationState: publication === 'all' ? undefined : [publication],
      qualityState: quality === 'all' ? undefined : [quality],
      providerDatasetId: submitted.providerDatasetId,
      hasIssue: issue === 'all' ? undefined : issue === 'yes',
      pageSize,
      cursor,
      sort,
      order,
    }),
    [cursor, issue, kind, lifecycle, order, pageSize, publication, quality, sort, submitted],
  );

  const featuresQuery = useQuery({
    queryKey: queryKeys.admin.features(params),
    queryFn: () => adminApi(apiClient).listFeatures(params),
    placeholderData: keepPreviousData,
  });

  const data = featuresQuery.data ?? null;
  const nextCursor = data?.next_cursor ?? null;
  const error = featuresQuery.isError
    ? featuresQuery.error instanceof ApiError
      ? featuresQuery.error.message
      : '조회 실패'
    : null;

  const onSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    // Map은 `provider_dataset_id`를 정수(>=1)로만 받는다 — 그 밖의 입력은 안 보낸다.
    const providerDatasetId = Number.parseInt(providerDatasetInput.trim(), 10);
    const validDatasetId = Number.isInteger(providerDatasetId) && providerDatasetId >= 1;
    setSubmitted({
      q: queryInput.trim(),
      providerDatasetId: validDatasetId ? providerDatasetId : undefined,
      categories: valuesFromCsv(categoryInput),
    });
    resetCursor();
  };

  const columns: AdminTableColumn<AdminFeatureSummary>[] = [
    {
      key: 'feature',
      header: 'feature',
      sortable: true,
      // 컬럼 id는 'feature'지만 서버 정렬 파라미터는 'name'이다.
      sortKey: 'name',
      sortValue: (feature) => feature.name,
      cell: (feature) => (
        <div>
          <div className="font-medium">{feature.name}</div>
          <div className="break-all font-mono text-xs text-muted">{feature.feature_id}</div>
        </div>
      ),
    },
    {
      key: 'kind',
      header: 'kind/state',
      sortable: true,
      sortValue: (feature) =>
        `${feature.kind}:${feature.lifecycle_state}:${feature.publication_state}:${feature.quality_state}`,
      cell: (feature) => (
        <div className="text-xs">
          <div>{feature.kind}</div>
          <StateAxes feature={feature} />
        </div>
      ),
    },
    {
      key: 'provider',
      header: 'provider',
      sortable: true,
      sortValue: (feature) => feature.primary_provider ?? '',
      cell: (feature) => (
        <div className="text-xs">
          <div>{feature.primary_provider ?? '—'}</div>
          <div className="text-muted">{feature.primary_dataset_key ?? '—'}</div>
        </div>
      ),
    },
    {
      key: 'issue_count',
      header: 'issues',
      sortable: true,
      sortValue: (feature) => feature.issue_count,
      align: 'right',
      cell: (feature) => feature.issue_count,
    },
    {
      key: 'coord',
      header: 'coord/address',
      cell: (feature) => (
        <div className="text-xs">
          <div className="font-mono">{coordLabel(feature)}</div>
          <div className="max-w-64 truncate text-muted">{feature.address_label ?? '—'}</div>
        </div>
      ),
    },
    {
      key: 'updated_at',
      header: 'updated',
      sortable: true,
      sortValue: (feature) => new Date(feature.updated_at).getTime(),
      cell: (feature) => formatDateTime(feature.updated_at),
    },
    {
      key: 'action',
      header: '',
      cell: (feature) => (
        <Button
          size="sm"
          variant="ghost"
          onClick={(event) => {
            event.stopPropagation();
            setSelectedFeatureId(feature.feature_id);
          }}
          data-testid={`admin-features-detail-${feature.feature_id}`}
        >
          <Eye aria-hidden="true" />
          상세
        </Button>
      ),
    },
  ];

  return (
    <AdminPage
      title="Features"
      description="kor-travel-map admin API 기반 feature 목록과 원천 상세 조회"
    >
      {/* 툴바는 한 묶음(space-y-3)으로 붙여 둔다 — AdminPage의 space-y-6은 섹션 간격이다. */}
      <div className="space-y-3">
        {/* 텍스트 3종만 제출로 적용된다(전환 전과 동일) — select는 form 밖에 두어 Firefox에서
            select 위 Enter가 폼을 제출하는 일이 없게 한다. */}
        <form onSubmit={onSearch}>
          <FilterBar>
            <FilterField className="w-56" htmlFor="admin-features-search" label="검색">
              <div className="relative">
                <Search
                  className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted"
                  aria-hidden="true"
                />
                <Input
                  id="admin-features-search"
                  type="search"
                  value={queryInput}
                  onChange={(event) => setQueryInput(event.target.value)}
                  className="pl-9"
                  placeholder="name, address, feature_id"
                  data-testid="admin-features-search"
                />
              </div>
            </FilterField>
            <FilterField className="w-36" hint="정수 1 이상" label="provider dataset ID">
              <Input
                type="number"
                min={1}
                step={1}
                value={providerDatasetInput}
                onChange={(event) => setProviderDatasetInput(event.target.value)}
                placeholder="provider_dataset_id"
                data-testid="admin-features-provider-dataset-filter"
              />
            </FilterField>
            <FilterField className="w-36" hint="쉼표로 여러 개" label="category">
              <Input
                type="text"
                value={categoryInput}
                onChange={(event) => setCategoryInput(event.target.value)}
                placeholder="category"
                data-testid="admin-features-category-filter"
              />
            </FilterField>
            <FilterActions>
              <Button type="submit" variant="outline" data-testid="admin-features-search-submit">
                조회
              </Button>
            </FilterActions>
          </FilterBar>
        </form>

        <FilterBar>
          <FilterField label="kind">
            <NativeSelect
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as KindFilter);
                resetCursor();
              }}
              data-testid="admin-features-kind-filter"
            >
              <NativeSelectOption value="all">kind 전체</NativeSelectOption>
              {FEATURE_KINDS.map((item) => (
                <NativeSelectOption key={item} value={item}>
                  {item}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterField label="lifecycle">
            <NativeSelect
              value={lifecycle}
              onChange={(event) => {
                setLifecycle(event.target.value as LifecycleFilter);
                resetCursor();
              }}
              data-testid="admin-features-lifecycle-filter"
            >
              <NativeSelectOption value="all">lifecycle 전체</NativeSelectOption>
              {LIFECYCLE_STATES.map((item) => (
                <NativeSelectOption key={item} value={item}>
                  {item}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterField label="publication">
            <NativeSelect
              value={publication}
              onChange={(event) => {
                setPublication(event.target.value as PublicationFilter);
                resetCursor();
              }}
              data-testid="admin-features-publication-filter"
            >
              <NativeSelectOption value="all">publication 전체</NativeSelectOption>
              {PUBLICATION_STATES.map((item) => (
                <NativeSelectOption key={item} value={item}>
                  {item}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterField label="quality">
            <NativeSelect
              value={quality}
              onChange={(event) => {
                setQuality(event.target.value as QualityFilter);
                resetCursor();
              }}
              data-testid="admin-features-quality-filter"
            >
              <NativeSelectOption value="all">quality 전체</NativeSelectOption>
              {QUALITY_STATES.map((item) => (
                <NativeSelectOption key={item} value={item}>
                  {item}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterField label="이슈">
            <NativeSelect
              value={issue}
              onChange={(event) => {
                setIssue(event.target.value as IssueFilter);
                resetCursor();
              }}
              data-testid="admin-features-issue-filter"
            >
              {ISSUE_FILTERS.map((item) => (
                <NativeSelectOption key={item.value} value={item.value}>
                  {item.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FilterField>
        </FilterBar>

        {/*
          정렬은 서버(`sort`/`order` 쿼리)에서 일어나고, 표 헤더 클릭도 **같은 상태**를 움직인다
          (`AdminTable`의 `serverSort`). 두 경로가 한 상태를 공유하므로 어느 쪽으로 바꿔도 전체
          정렬이 바뀐다. 툴바 select를 남기는 이유는 `created_at`처럼 표에 대응 컬럼이 없는 정렬
          축이 있고, 방향만 따로 고르는 경로도 필요하기 때문이다.
        */}
        <FilterBar>
          <FilterField htmlFor="admin-features-sort" label="정렬">
            <NativeSelect
              id="admin-features-sort"
              value={sort}
              onChange={(event) => {
                setSort(event.target.value as AdminFeatureSort);
                resetCursor();
              }}
              data-testid="admin-features-sort-filter"
            >
              {SORT_OPTIONS.map((item) => (
                <NativeSelectOption key={item} value={item}>
                  {item}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterField label="정렬 방향">
            <NativeSelect
              value={order}
              onChange={(event) => {
                setOrder(event.target.value as AdminFeatureSortOrder);
                resetCursor();
              }}
              data-testid="admin-features-order-filter"
            >
              <NativeSelectOption value="asc">asc</NativeSelectOption>
              <NativeSelectOption value="desc">desc</NativeSelectOption>
            </NativeSelect>
          </FilterField>
          <FilterField label="페이지 크기">
            <NativeSelect
              value={String(pageSize)}
              onChange={(event) => {
                setPageSize(Number(event.target.value) as typeof pageSize);
                resetCursor();
              }}
              data-testid="admin-features-page-size"
            >
              {PAGE_SIZE_OPTIONS.map((item) => (
                <NativeSelectOption key={item} value={item}>
                  {item}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </FilterField>
          <FilterActions>
            <Button
              variant="outline"
              loading={featuresQuery.isFetching}
              onClick={() => void featuresQuery.refetch()}
              data-testid="admin-features-refresh"
            >
              <RefreshCw aria-hidden="true" />
              갱신
            </Button>
          </FilterActions>
          <span className="ml-auto text-xs text-muted">
            {data?.items.length ?? 0}행 / page {pageIndex}
            {data?.duration_ms !== null && data?.duration_ms !== undefined
              ? ` / ${data.duration_ms}ms`
              : ''}
          </span>
        </FilterBar>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="admin-features-error"
        >
          {error}
        </p>
      )}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_28rem]">
        <div className="min-w-0 space-y-3">
          <AdminTable
            columns={columns}
            rows={data?.items ?? []}
            loading={featuresQuery.isLoading}
            rowKey={(feature) => feature.feature_id}
            rowTestId={(feature) => `admin-features-row-${feature.feature_id}`}
            onRowClick={(feature) => setSelectedFeatureId(feature.feature_id)}
            empty="feature가 없습니다."
            ariaLabel="Feature 목록"
            // 헤더 클릭이 툴바 select와 **같은 서버 상태**를 움직인다. 예전에는 헤더가 현재
            // 페이지 안에서만 도는 클라이언트 정렬이라, 사용자에게는 전체가 정렬된 것처럼
            // 보이지만 실제로는 한 페이지 창만 뒤집혔다.
            serverSort={{
              key: sort,
              order,
              onChange: (nextSort, nextOrder) => {
                if (!isFeatureSort(nextSort)) {
                  // 서버가 모르는 키다. 정렬을 바꾸지 않는 편이 잘못된 목록을 보여주는 것보다 낫다.
                  console.warn(`[admin/features] 알 수 없는 정렬 키: ${nextSort}`);
                  return;
                }
                setSort(nextSort);
                setOrder(nextOrder);
                resetCursor();
              },
            }}
          />

          {/*
            cursor 스택을 들고 있지만 `previous`는 넘기지 않는다 — 전환 전에도 `이전`은 없었고
            (첫 페이지 / 다음 두 개뿐) 여기서 켜면 요청 밖의 동작 변경이 된다. 필요해지면
            `previous={{ available: cursorStack.length > 0, onActivate: pop }}` 한 줄이면 된다.
          */}
          <CursorPager
            hasNext={Boolean(nextCursor)}
            isFetching={featuresQuery.isFetching}
            isFirst={cursorStack.length === 0}
            placement="bottom"
            summary={<>페이지 {pageIndex}</>}
            onFirst={resetCursor}
            onNext={() => {
              if (!nextCursor) return;
              setCursorStack((stack) => [...stack, nextCursor]);
              setSelectedFeatureId(null);
            }}
          />
        </div>

        <DetailInspector featureId={selectedFeatureId} />
      </section>
    </AdminPage>
  );
}
