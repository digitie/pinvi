'use client';

import { VirtualTable, type RowData, type VirtualTableProps } from '@kor-travel/ui/virtual-table';
export { VirtualTableClampCell as DataTableClampCell } from '@kor-travel/ui/virtual-table';
export type {
  VirtualTableColumnMeta as DataTableColumnMeta,
  VirtualTableEmptyState as DataTableEmptyState,
  VirtualTableProps as DataTableProps,
} from '@kor-travel/ui/virtual-table';

/** 기존 admin 정렬 셀렉터를 공통 표의 테스트 계약에 연결한다. */
export function DataTable<T extends RowData>(props: VirtualTableProps<T>) {
  return (
    <VirtualTable
      {...props}
      sortButtonTestIdPrefix={props.sortButtonTestIdPrefix ?? 'admin-table-sort-'}
      containerClassName={['group-data-[slot=card]/card:border-0', props.containerClassName]
        .filter(Boolean)
        .join(' ')}
      rowProps={(row) => ({
        ...props.rowProps?.(row),
        ...(props.onRowClick ? { 'data-clickable': '' } : {}),
      })}
    />
  );
}
