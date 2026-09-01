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

  // 가상화는 실제로 임계 행수를 넘길 때만 켠다(1행 e2e mock 안정성 — 기존 동작 유지).
  const useVirtual = virtualized && rows.length > virtualizeThreshold;
  const showMobileCards = mobileCard != null && !loading && rows.length > 0;

  return (
    <>
      {showMobileCards && (
        <div className="space-y-2 md:hidden" data-testid="admin-mobile-cards">
          {rows.map((row) => (
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
          emptyMessage={empty}
          manualSorting={false}
          sorting={undefined}
          onRowClick={onRowClick}
          rowTestId={rowTestId}
          virtualized={useVirtual}
          containerStyle={useVirtual ? { maxHeight } : undefined}
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
