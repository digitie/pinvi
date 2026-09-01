'use client';

import { type ReactNode, useMemo } from 'react';
import type { ColumnDef } from '@tanstack/react-table';

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
  /** 정렬 비교용 값. `sortable`이면 필수. 렌더는 항상 `cell`이 담당. */
  sortValue?: (row: R) => string | number;
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
}: AdminTableProps<R>) {
  const tableColumns = useMemo<ColumnDef<R, unknown>[]>(
    () =>
      columns.map((col) => {
        const canSort = Boolean(enableSorting && col.sortable && col.sortValue);
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
        return canSort ? { ...base, accessorFn: (row: R) => col.sortValue!(row) } : base;
      }),
    [columns, enableSorting],
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
          manualSorting={false}
          sorting={undefined}
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
