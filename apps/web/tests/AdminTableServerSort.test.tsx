import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

/**
 * 서버 정렬 연동을 잠근다(T-357).
 *
 * `serverSort` 없이 헤더를 클릭하면 `getSortedRowModel`이 **현재 페이지 안에서만** 정렬한다.
 * cursor/offset 페이징 목록에서 그건 화면이 거짓말을 하는 것이다 — 사용자는 전체가 정렬된 줄
 * 알지만 실제로는 20행짜리 창만 뒤집힌다. `features` 페이지가 정확히 그 상태였고, 툴바 select는
 * 서버 정렬이라 두 컨트롤이 서로를 모르고 있었다.
 */
interface Row {
  id: string;
  name: string;
  count: number;
}

const ROWS: Row[] = [
  { id: '1', name: 'Charlie', count: 30 },
  { id: '2', name: 'Alice', count: 10 },
  { id: '3', name: 'Bob', count: 20 },
];

const COLUMNS: AdminTableColumn<Row>[] = [
  // 컬럼 id와 서버 정렬 키가 다른 경우(features의 feature ↔ name)를 재현한다.
  { key: 'feature', header: '이름', sortable: true, sortKey: 'name', cell: (r) => r.name },
  { key: 'count', header: '건수', sortable: true, cell: (r) => r.count, align: 'right' },
];

function cells() {
  return Array.from(document.querySelectorAll('tbody tr')).map(
    (tr) => tr.querySelector('td')?.textContent ?? '',
  );
}

describe('AdminTable — 서버 정렬 연동', () => {
  it('헤더 클릭이 서버 정렬 키로 변환돼 전달된다 (컬럼 id != 서버 키)', () => {
    const onChange = vi.fn();
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        serverSort={{ key: 'name', order: 'asc', onChange }}
      />,
    );

    fireEvent.click(screen.getByTestId('admin-table-sort-feature'));
    // 같은 축을 다시 누르면 방향만 뒤집힌다.
    expect(onChange).toHaveBeenCalledWith('name', 'desc');
  });

  it('다른 컬럼을 누르면 그 컬럼의 서버 키로 오름차순부터 시작한다', () => {
    const onChange = vi.fn();
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        serverSort={{ key: 'name', order: 'asc', onChange }}
      />,
    );

    fireEvent.click(screen.getByTestId('admin-table-sort-count'));
    expect(onChange).toHaveBeenCalledWith('count', 'asc');
  });

  it('서버가 준 정렬 축이 헤더에 aria-sort로 반영된다', () => {
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        serverSort={{ key: 'name', order: 'desc', onChange: () => {} }}
      />,
    );

    expect(screen.getByRole('columnheader', { name: /이름/ })).toHaveAttribute(
      'aria-sort',
      'descending',
    );
    expect(screen.getByRole('columnheader', { name: /건수/ })).toHaveAttribute('aria-sort', 'none');
  });

  it('서버 정렬 모드에서는 행 순서를 클라이언트가 다시 뒤집지 않는다', () => {
    // 서버가 이미 정렬해 보낸 순서를 그대로 보여야 한다. 여기서 클라이언트가 또 정렬하면
    // 서버 정렬 축과 화면이 어긋난다.
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        serverSort={{ key: 'name', order: 'asc', onChange: () => {} }}
      />,
    );

    expect(cells()).toEqual(['Charlie', 'Alice', 'Bob']);
  });

  it('표에 없는 정렬 축이면 어느 헤더도 활성으로 표시하지 않는다', () => {
    // features의 `created_at`처럼 툴바 select로만 고를 수 있는 축이 있다.
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        serverSort={{ key: 'created_at', order: 'asc', onChange: () => {} }}
      />,
    );

    expect(screen.getByRole('columnheader', { name: /이름/ })).toHaveAttribute('aria-sort', 'none');
    expect(screen.getByRole('columnheader', { name: /건수/ })).toHaveAttribute('aria-sort', 'none');
  });

  it('serverSort가 없으면 기존 클라이언트 정렬이 그대로 동작한다', () => {
    render(
      <AdminTable
        columns={[{ ...COLUMNS[0]!, sortValue: (r) => r.name }, COLUMNS[1]!]}
        rows={ROWS}
        rowKey={(r) => r.id}
      />,
    );

    expect(cells()).toEqual(['Charlie', 'Alice', 'Bob']);
    fireEvent.click(screen.getByTestId('admin-table-sort-feature'));
    expect(cells()).toEqual(['Alice', 'Bob', 'Charlie']);
  });
});
