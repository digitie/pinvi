'use client';

import { type ReactNode, type RefObject, useMemo, useRef, useState } from 'react';
import {
  type ColumnDef,
  type Row,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import { computeSpacerWindow } from '@/lib/adminTableWindow';

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
  /** 안정적 행 testid(e2e). 예: `(u) => `admin-users-row-${u.user_id}``. */
  rowTestId?: (row: R) => string;
  /** 행 가상화 활성화(로그 등 대형 리스트). 작은 리스트는 threshold로 전 행 렌더. */
  virtualized?: boolean;
  /** 가상화 시 스크롤 컨테이너 최대 높이. */
  maxHeight?: string;
  /** 이 행수 이하이면 가상화하지 않고 전 행 렌더(1행 e2e mock 안정성). */
  virtualizeThreshold?: number;
  /** 전체 정렬 토글(개별은 컬럼 `sortable`). */
  enableSorting?: boolean;
  initialSort?: { columnKey: string; desc: boolean };
}

interface AdminColumnMeta {
  width?: string;
  align?: 'left' | 'right';
}

const DEFAULT_ROW_HEIGHT = 41;

/**
 * 가상화 본문 — `virtualized`가 실제로 동작할 때만 마운트한다(비가상 테이블은 이 컴포넌트를
 * 렌더하지 않아 useVirtualizer/observer 비용·리렌더 churn이 전혀 없다). 위/아래 스페이서 `<tr>`로
 * 스크롤 높이를 채워 네이티브 `<table>` 컬럼 폭과 role을 유지한다.
 */
function VirtualRows<R>({
  scrollRef,
  rows,
  renderRow,
  colCount,
}: {
  scrollRef: RefObject<HTMLDivElement | null>;
  rows: Row<R>[];
  renderRow: (row: Row<R>) => ReactNode;
  colCount: number;
}) {
  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => DEFAULT_ROW_HEIGHT,
    overscan: 10,
  });
  const items = virtualizer.getVirtualItems();
  const { paddingTop, paddingBottom } = computeSpacerWindow(items, virtualizer.getTotalSize());
  return (
    <>
      {paddingTop > 0 && (
        <tr aria-hidden="true">
          <td colSpan={colCount} style={{ height: paddingTop, padding: 0, border: 0 }} />
        </tr>
      )}
      {items.map((vi) => {
        const row = rows[vi.index];
        return row ? renderRow(row) : null;
      })}
      {paddingBottom > 0 && (
        <tr aria-hidden="true">
          <td colSpan={colCount} style={{ height: paddingBottom, padding: 0, border: 0 }} />
        </tr>
      )}
    </>
  );
}

/**
 * Admin 공통 테이블 — `@tanstack/react-table`(headless) + `@tanstack/react-virtual` 기반.
 * 시맨틱 `<table>`을 유지해 a11y/role 기반 e2e를 보존하고, 가상화는 스페이서 `<tr>`로 스크롤
 * 높이를 채워(네이티브 컬럼 폭 유지) 보이는 행만 렌더한다. 헤더 클릭 정렬은 클라이언트 측이며
 * 페이지네이션 테이블에서는 현재 페이지 한정이다.
 */
export function AdminTable<R>({
  columns,
  rows,
  rowKey,
  empty = '항목이 없습니다.',
  loading = false,
  onRowClick,
  rowTestId,
  virtualized = false,
  maxHeight = '70vh',
  virtualizeThreshold = 30,
  enableSorting = true,
  initialSort,
}: AdminTableProps<R>) {
  const [sorting, setSorting] = useState<SortingState>(
    initialSort ? [{ id: initialSort.columnKey, desc: initialSort.desc }] : [],
  );

  const tableColumns = useMemo<ColumnDef<R>[]>(
    () =>
      columns.map((col) => {
        const canSort = Boolean(col.sortable && col.sortValue);
        const meta: AdminColumnMeta = { width: col.width, align: col.align };
        const base: ColumnDef<R> = {
          id: col.key,
          header: col.header,
          cell: (ctx) => col.cell(ctx.row.original),
          enableSorting: canSort,
          meta,
        };
        return canSort ? { ...base, accessorFn: (row: R) => col.sortValue!(row) } : base;
      }),
    [columns],
  );

  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getRowId: (row) => rowKey(row),
    enableSorting,
    enableMultiSort: false,
    // 숫자 컬럼도 첫 클릭은 오름차순(TanStack 기본은 숫자=내림차순 우선) — admin 일관 UX.
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  const tableRows = table.getRowModel().rows;
  const colCount = columns.length;

  const scrollRef = useRef<HTMLDivElement>(null);
  const useVirtual = virtualized && tableRows.length > virtualizeThreshold;

  const renderRow = (row: Row<R>) => (
    <tr
      key={row.id}
      data-testid={rowTestId ? rowTestId(row.original) : undefined}
      className={onRowClick ? 'cursor-pointer hover:bg-surface-soft' : undefined}
      onClick={onRowClick ? () => onRowClick(row.original) : undefined}
    >
      {row.getVisibleCells().map((cell) => {
        const align = (cell.column.columnDef.meta as AdminColumnMeta | undefined)?.align;
        return (
          <td
            key={cell.id}
            className={`whitespace-nowrap px-3 py-2 text-ink ${align === 'right' ? 'text-right' : ''}`}
          >
            {flexRender(cell.column.columnDef.cell, cell.getContext())}
          </td>
        );
      })}
    </tr>
  );

  let body: ReactNode;
  if (loading) {
    body = (
      <tr>
        <td colSpan={colCount} className="px-3 py-6 text-center text-muted">
          불러오는 중...
        </td>
      </tr>
    );
  } else if (tableRows.length === 0) {
    body = (
      <tr>
        <td colSpan={colCount} className="px-3 py-6 text-center text-muted">
          {empty}
        </td>
      </tr>
    );
  } else if (useVirtual) {
    body = (
      <VirtualRows scrollRef={scrollRef} rows={tableRows} renderRow={renderRow} colCount={colCount} />
    );
  } else {
    body = tableRows.map((row) => renderRow(row));
  }

  return (
    <div
      ref={scrollRef}
      data-testid="admin-table-scroll"
      // 비가상 테이블은 원래 DataTable처럼 가로 스크롤만(세로 스크롤바 feedback loop 회피).
      // 가상화 테이블만 세로 스크롤(overflow-auto)을 켜 윈도잉이 동작하게 한다.
      className={`${virtualized ? 'overflow-auto' : 'overflow-x-auto'} rounded-sm border border-hairline`}
      style={virtualized ? { maxHeight } : undefined}
    >
      <table className="min-w-full divide-y divide-hairline text-sm">
        <colgroup>
          {columns.map((col) => (
            <col key={col.key} style={col.width ? { width: col.width } : undefined} />
          ))}
        </colgroup>
        {/* sticky 헤더는 실제 세로 스크롤이 있는 가상화 테이블에만. 비가상(content-fit)은 스크롤이
            없어 sticky가 무의미하고, z-20 stacking이 z-index 없는 모달 위로 올라와 클릭을 가로채는
            문제(상세 페이지 상태변경 모달)를 일으킨다. */}
        <thead className={virtualized ? 'sticky top-0 z-20 bg-surface-soft' : 'bg-surface-soft'}>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                const canSort = header.column.getCanSort();
                const sorted = header.column.getIsSorted();
                const align = (header.column.columnDef.meta as AdminColumnMeta | undefined)?.align;
                const headerNode = flexRender(
                  header.column.columnDef.header,
                  header.getContext(),
                );
                return (
                  <th
                    key={header.id}
                    scope="col"
                    aria-sort={
                      sorted === 'asc'
                        ? 'ascending'
                        : sorted === 'desc'
                          ? 'descending'
                          : canSort
                            ? 'none'
                            : undefined
                    }
                    className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted ${align === 'right' ? 'text-right' : 'text-left'}`}
                  >
                    {canSort ? (
                      <button
                        type="button"
                        onClick={header.column.getToggleSortingHandler()}
                        className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-ink"
                        data-testid={`admin-table-sort-${header.column.id}`}
                      >
                        {headerNode}
                        {sorted === 'asc' ? (
                          <ArrowUp className="h-3 w-3" aria-hidden="true" />
                        ) : sorted === 'desc' ? (
                          <ArrowDown className="h-3 w-3" aria-hidden="true" />
                        ) : (
                          <ChevronsUpDown className="h-3 w-3 opacity-50" aria-hidden="true" />
                        )}
                      </button>
                    ) : (
                      headerNode
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-hairline bg-white">{body}</tbody>
      </table>
    </div>
  );
}
