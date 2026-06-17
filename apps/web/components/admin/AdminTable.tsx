'use client';

import { type ReactNode, useMemo, useRef, useState } from 'react';
import {
  type ColumnDef,
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
 * Admin 공통 테이블 — `@tanstack/react-table`(headless) + `@tanstack/react-virtual` 기반.
 * 시맨틱 `<table>`을 유지해 a11y/role 기반 e2e를 보존하고, 가상화는 위/아래 스페이서 `<tr>`로
 * 스크롤 높이를 채워(네이티브 컬럼 폭 유지) 보이는 행만 렌더한다. 헤더 클릭 정렬은 클라이언트
 * 측이며 페이지네이션 테이블에서는 현재 페이지 한정이다.
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
  const virtualizer = useVirtualizer({
    count: tableRows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => DEFAULT_ROW_HEIGHT,
    overscan: 10,
    enabled: useVirtual,
  });

  const renderRow = (row: (typeof tableRows)[number]) => (
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
    const items = virtualizer.getVirtualItems();
    const { paddingTop, paddingBottom } = computeSpacerWindow(items, virtualizer.getTotalSize());
    body = (
      <>
        {paddingTop > 0 && (
          <tr aria-hidden="true">
            <td colSpan={colCount} style={{ height: paddingTop, padding: 0, border: 0 }} />
          </tr>
        )}
        {items.map((vi) => {
          const row = tableRows[vi.index];
          return row ? renderRow(row) : null;
        })}
        {paddingBottom > 0 && (
          <tr aria-hidden="true">
            <td colSpan={colCount} style={{ height: paddingBottom, padding: 0, border: 0 }} />
          </tr>
        )}
      </>
    );
  } else {
    body = tableRows.map((row) => renderRow(row));
  }

  return (
    <div
      ref={scrollRef}
      data-testid="admin-table-scroll"
      className="overflow-auto rounded-sm border border-hairline"
      style={virtualized ? { maxHeight } : undefined}
    >
      <table className="min-w-full divide-y divide-hairline text-sm">
        <colgroup>
          {columns.map((col) => (
            <col key={col.key} style={col.width ? { width: col.width } : undefined} />
          ))}
        </colgroup>
        <thead className="sticky top-0 z-20 bg-surface-soft">
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
