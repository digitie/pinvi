// 하위호환 shim — 기존 import 경로(`@/components/admin/DataTable`)를 유지한다.
// 실제 구현은 `AdminTable`(@tanstack/react-table + react-virtual 기반). 신규 코드는
// `AdminTable`/`AdminTableColumn`을 직접 import한다.
export { AdminTable as DataTable } from './AdminTable';
export type {
  AdminTableColumn as DataTableColumn,
  AdminTableProps as DataTableProps,
} from './AdminTable';
