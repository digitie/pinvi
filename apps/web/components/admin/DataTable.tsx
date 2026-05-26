'use client';

import type { ReactNode } from 'react';

export interface DataTableColumn<R> {
  key: string;
  header: string;
  width?: string;
  cell: (row: R) => ReactNode;
}

export interface DataTableProps<R> {
  columns: DataTableColumn<R>[];
  rows: R[];
  empty?: string;
  loading?: boolean;
  onRowClick?: (row: R) => void;
  rowKey: (row: R) => string;
}

/** Admin 공통 DataTable — 단순 thead + tbody. SPEC V8 M-3. */
export function DataTable<R>({
  columns,
  rows,
  empty = '항목이 없습니다.',
  loading = false,
  onRowClick,
  rowKey,
}: DataTableProps<R>) {
  return (
    <div className="overflow-x-auto rounded-sm border border-hairline">
      <table className="min-w-full divide-y divide-hairline text-sm">
        <thead className="bg-surface-soft">
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted"
                style={col.width ? { width: col.width } : undefined}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline bg-white">
          {loading ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-muted">
                불러오는 중...
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-muted">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={rowKey(row)}
                className={
                  onRowClick ? 'cursor-pointer hover:bg-surface-soft' : undefined
                }
                onClick={() => onRowClick?.(row)}
              >
                {columns.map((col) => (
                  <td key={col.key} className="whitespace-nowrap px-3 py-2 text-ink">
                    {col.cell(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
