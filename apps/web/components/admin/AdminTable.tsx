'use client';

import { type ReactNode, useCallback, useMemo } from 'react';
import type { ColumnDef, OnChangeFn, SortingState } from '@tanstack/react-table';

import { DataTable, type DataTableColumnMeta } from '@/components/admin/ui/data-table';

/**
 * Admin 공통 테이블 — kor-travel-map admin의 `DataTable` 위에 얹은 **어댑터**다(T-356).
 *
 * 왜 어댑터인가: 이 컴포넌트를 쓰는 admin 페이지가 36곳이다. `AdminTableColumn` API를 그대로
 * 유지하면 그 36곳을 한 줄도 고치지 않고 KTM 표의 외관과 상태 표면(skeleton·error·retry·
 * 행 선택·키보드 접근성)을 그대로 얻는다. 페이지별 `ColumnDef` 직접 전환은 후속 단계에서
 * 선택적으로 진행한다.
 *
 * 기존 동작 중 계약으로 보존하는 것(테스트·e2e가 잠그고 있다):
 *   - `data-testid="admin-table-scroll"` 스크롤 컨테이너
 *   - `data-testid="admin-table-sort-<columnKey>"` 정렬 버튼 (DataTable 쪽에 부착)
 *   - `data-testid="admin-mobile-cards"` 모바일 카드 목록 (KTM에는 없는 pinvi 고유 기능)
 *   - 빈 목록 문구 `항목이 없습니다.`
 *   - 로딩 중 `불러오는 중…` — KTM은 skeleton 행만 그리는데, 여러 e2e가 이 문구가 사라지는
 *     것으로 로딩 완료를 판정한다. 문구를 없애면 그 대기가 조용히 무의미해지므로(항상 0건)
 *     skeleton은 KTM대로 그리되 같은 문구를 sr-only로 함께 둔다 — 스크린리더에도 이득이다.
 *
 * 기본값 차이 하나: KTM `DataTable`은 서버 정렬이 일반적이라 `manualSorting` 기본이 true다.
 * pinvi `AdminTable`은 지금까지 클라이언트 정렬만 했으므로 어댑터는 `manualSorting={false}`로
 * 고정해 기존 동작을 유지한다(서버 정렬이 필요한 페이지는 `DataTable`을 직접 쓰면 된다).
 */
export interface AdminTableColumn<R> {
  key: string;
  header: string;
  width?: string;
  cell: (row: R) => ReactNode;
  /** 헤더 클릭 정렬 활성화. 정렬 키는 `sortValue`로만 결정(렌더 결과로 정렬하지 않음). */
  sortable?: boolean;
  /** 정렬 비교용 값. `sortable`이면 필수(서버 정렬 모드에서는 불필요). 렌더는 항상 `cell`이 담당. */
  sortValue?: (row: R) => string | number;
  /**
   * 서버 정렬 파라미터 이름. `serverSort`를 쓸 때만 의미가 있고, 없으면 `key`를 그대로 쓴다.
   * 컬럼 key와 서버 정렬 키가 다를 때 필요하다(예: 컬럼 `feature` → 서버 `name`).
   */
  sortKey?: string;
  align?: 'left' | 'right';
}

export interface AdminTableProps<R> {
  columns: AdminTableColumn<R>[];
  rows: R[];
  rowKey: (row: R) => string;
  empty?: string;
  loading?: boolean;
  onRowClick?: (row: R) => void;
  /** 안정적 행 testid(e2e). */
  rowTestId?: (row: R) => string;
  /** 행 가상화 활성화(로그 등 대형 리스트). */
  virtualized?: boolean;
  /** 가상화 시 스크롤 컨테이너 최대 높이. */
  maxHeight?: string;
  /** 이 행수 이하이면 가상화하지 않고 전 행 렌더(1행 e2e mock 안정성). */
  virtualizeThreshold?: number;
  /** 작은 화면에서 표 대신 렌더할 행 요약. */
  mobileCard?: (row: R) => ReactNode;
  /** 전체 정렬 토글(개별은 컬럼 `sortable`). */
  enableSorting?: boolean;
  initialSort?: { columnKey: string; desc: boolean };
  /**
   * 서버 정렬 연동(T-357). 주면 헤더 클릭이 **클라이언트 정렬 대신 서버 쿼리**를 바꾼다.
   *
   * 없으면 헤더 정렬은 `getSortedRowModel`로 도는 클라이언트 정렬이고, 그건 **현재 페이지
   * 안에서만** 유효하다. cursor/offset 페이징 목록에서 그대로 두면 사용자에게 "전체가 정렬된 것
   * 처럼" 보이지만 실제로는 20행짜리 창만 뒤집힌다 — 화면이 거짓말을 한다.
   *
   * `key`는 서버 파라미터 값이고 컬럼의 `sortKey ?? key`와 대응한다. 목록에 없는 키가 오면
   * 아무 헤더도 활성으로 표시되지 않는다(툴바 select로만 고를 수 있는 정렬 축이 있을 수 있다).
   */
  serverSort?: {
    key: string;
    order: 'asc' | 'desc';
    onChange: (key: string, order: 'asc' | 'desc') => void;
  };
  /** 표의 접근성 이름. 주지 않으면 한 화면에 표가 둘 이상일 때 스크린리더가 구분하지 못한다. */
  ariaLabel?: string;
  /** 조회 실패 표면 — 주면 표 대신 what/why/다시 시도 Alert를 렌더한다. */
  isError?: boolean;
  error?: { message?: string } | null;
  /** `다시 시도` 버튼에 연결할 refetch. Promise를 돌려주면 resolve까지 버튼이 잠긴다. */
  onRetry?: () => void | Promise<unknown>;
}

/**
 * `width: '80px'` 같은 px 폭을 TanStack의 `size`(숫자)로 옮긴다. 가상화 경로는 native
 * table layout이 아니라 flex라 셀 폭이 전적으로 `column.getSize()`에서 나오므로, size를
 * 주지 않으면 지정 폭이 무시되고 TanStack 기본값(150px)이 적용된다.
 */
function pxWidthToSize(width: string | undefined): number | undefined {
  if (!width) return undefined;
  const match = /^(\d+(?:\.\d+)?)px$/.exec(width.trim());
  return match ? Number(match[1]) : undefined;
}

export function AdminTable<R>({
  columns,
  rows,
  rowKey,
  empty = '항목이 없습니다.',
  loading = false,
  onRowClick,
  rowTestId,
  virtualized = false,
  maxHeight = '70dvh',
  virtualizeThreshold = 30,
  mobileCard,
  enableSorting = true,
  initialSort,
  ariaLabel,
  isError,
  error,
  onRetry,
  serverSort,
}: AdminTableProps<R>) {
  const tableColumns = useMemo<ColumnDef<R, unknown>[]>(
    () =>
      columns.map((col) => {
        // 서버 정렬 모드에서는 `sortValue`가 필요 없다 — 비교를 서버가 한다.
        const canSort = Boolean(
          enableSorting && col.sortable && (serverSort ? true : col.sortValue),
        );
        const meta: DataTableColumnMeta = {
          align: col.align,
          // KTM DataTable에는 <colgroup>이 없다 — 폭은 헤더 셀로 옮긴다. 클래스가 아니라
          // inline style인 이유: `col.width`는 런타임 값이라 `w-[...]`로 조립하면 Tailwind가
          // 정적 추출을 못 해 CSS가 생성되지 않는다(폭이 조용히 사라진다).
          headerStyle: col.width ? { width: col.width } : undefined,
        };
        const size = pxWidthToSize(col.width);
        const base: ColumnDef<R, unknown> = {
          id: col.key,
          header: col.header,
          cell: (ctx) => col.cell(ctx.row.original),
          enableSorting: canSort,
          ...(size === undefined ? {} : { size }),
          // TanStack 기본은 숫자 컬럼의 첫 클릭이 내림차순이다. admin은 컬럼 종류와 무관하게
          // 첫 클릭을 오름차순으로 통일해 왔고 단위 테스트가 그 동작을 잠그고 있다.
          sortDescFirst: false,
          meta,
        };
        if (!canSort) return base;
        // TanStack `getCanSort()`는 `accessorFn` 존재를 요구한다 — 없으면 정렬 버튼 자체가
        // 렌더되지 않는다. 서버 정렬 모드에서도 accessor는 남기되, `manualSorting`이 켜져 있어
        // `getSortedRowModel`이 돌지 않으므로 이 값으로 행이 재정렬되지는 않는다.
        // 서버 모드에서 `sortValue`가 없는 컬럼은 상수 accessor로 충분하다(비교는 서버 몫).
        const accessorFn = col.sortValue ?? (() => '');
        return { ...base, accessorFn: (row: R) => accessorFn(row) };
      }),
    [columns, enableSorting, serverSort],
  );

  // ── 서버 정렬 연동 ──
  // 서버 파라미터(`key`/`order`)를 TanStack `SortingState`로 비추고, 헤더 클릭을 다시 서버
  // 파라미터로 되돌린다. 컬럼 id는 `col.key`이고 서버 키는 `col.sortKey ?? col.key`라 양방향
  // 매핑이 필요하다(예: 컬럼 `feature` ↔ 서버 `name`).
  const serverSortState = useMemo<SortingState | undefined>(() => {
    if (!serverSort) return undefined;
    const column = columns.find((col) => (col.sortKey ?? col.key) === serverSort.key);
    // 서버 정렬 축이 어느 컬럼에도 없을 수 있다(툴바 select 전용 축). 그때는 활성 헤더가 없다.
    if (!column) return [];
    return [{ id: column.key, desc: serverSort.order === 'desc' }];
  }, [serverSort, columns]);

  const handleServerSortingChange = useCallback<OnChangeFn<SortingState>>(
    (updater) => {
      if (!serverSort) return;
      const next = typeof updater === 'function' ? updater(serverSortState ?? []) : updater;
      const first = next[0];
      // 세 번째 클릭은 정렬 해제인데, 서버 목록은 정렬 없이 조회할 수 없다(cursor 안정성).
      // 그래서 해제 대신 현재 축을 유지한다.
      if (!first) return;
      const column = columns.find((col) => col.key === first.id);
      if (!column) return;
      serverSort.onChange(column.sortKey ?? column.key, first.desc ? 'desc' : 'asc');
    },
    [serverSort, serverSortState, columns],
  );

  // `virtualized` prop과 **실제 윈도잉**을 분리한다.
  //
  // pinvi에서 이 prop의 의미는 "높이를 제한하고 세로로 스크롤한다"이고, DOM 윈도잉은 행이
  // 임계(기본 30)를 넘을 때만 켠다(1행 e2e mock 안정성). 둘을 한 플래그로 묶으면 3행짜리
  // 로그 표에서 sticky 헤더와 maxHeight가 함께 사라진다 —
  // `e2e/admin-table.e2e.ts`가 정확히 3행으로 sticky를 잠그고 있고, 로그 필터를 좁게 걸면
  // 표 내부 스크롤이 페이지 전체 스크롤로 튄다.
  const useVirtual = virtualized && rows.length > virtualizeThreshold;
  const showMobileCards = mobileCard != null && !loading && rows.length > 0;

  // 모바일 카드는 표와 같은 순서로 보여야 한다. 표는 DataTable 내부에서 정렬되므로 여기서는
  // `initialSort`만 재현한다(모바일에서는 헤더가 `hidden`이라 정렬을 바꿀 수단이 없어 초기
  // 정렬이 곧 최종 순서다). 정렬 지정이 없으면 원본 순서를 그대로 쓴다.
  const mobileRows = useMemo(() => {
    if (!showMobileCards || !initialSort) return rows;
    const column = columns.find((col) => col.key === initialSort.columnKey);
    if (!column?.sortValue) return rows;
    const sortValue = column.sortValue;
    const direction = initialSort.desc ? -1 : 1;
    return [...rows].sort((a, b) => {
      const left = sortValue(a);
      const right = sortValue(b);
      if (left === right) return 0;
      return (left < right ? -1 : 1) * direction;
    });
  }, [showMobileCards, initialSort, rows, columns]);

  return (
    <>
      {showMobileCards && (
        <div className="space-y-2 md:hidden" data-testid="admin-mobile-cards">
          {mobileRows.map((row) => (
            <div key={rowKey(row)}>{mobileCard(row)}</div>
          ))}
        </div>
      )}
      <div className={showMobileCards ? 'hidden md:block' : undefined}>
        {loading && <span className="sr-only">불러오는 중…</span>}
        <DataTable<R>
          columns={tableColumns}
          data={rows}
          getRowId={(row) => rowKey(row)}
          isLoading={loading}
          isError={isError}
          error={error}
          onRetry={onRetry}
          ariaLabel={ariaLabel}
          emptyMessage={empty}
          // 서버 정렬 모드면 TanStack에게 비교를 맡기지 않고(제어) 헤더 클릭을 쿼리로 돌린다.
          manualSorting={Boolean(serverSort)}
          sorting={serverSortState}
          onSortingChange={serverSort ? handleServerSortingChange : undefined}
          onRowClick={onRowClick}
          rowTestId={rowTestId}
          virtualized={useVirtual}
          stickyHeader={virtualized}
          // Table 컨테이너 기본은 `overflow-x-auto`다. 높이를 제한하면 세로도 스크롤해야 하므로
          // 명시적으로 양축을 연다(구버전도 가상화일 때 `overflow-auto`였다).
          containerClassName={virtualized ? 'overflow-auto' : undefined}
          containerStyle={virtualized ? { maxHeight } : undefined}
          // `admin-table-scroll`은 e2e가 **직접 스크롤**하는 요소다(`el.scrollTo`). 바깥 래퍼가
          // 아니라 DataTable 내부의 진짜 스크롤 컨테이너가 이 testid를 가져야 한다.
          containerTestId="admin-table-scroll"
          initialSorting={
            initialSort ? [{ id: initialSort.columnKey, desc: initialSort.desc }] : undefined
          }
        />
      </div>
    </>
  );
}
