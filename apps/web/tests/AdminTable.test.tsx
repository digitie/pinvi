import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

interface Row {
  id: string;
  name: string;
  age: number;
}

const ROWS: Row[] = [
  { id: '1', name: 'Charlie', age: 30 },
  { id: '2', name: 'Alice', age: 20 },
  { id: '3', name: 'Bob', age: 25 },
];

const COLUMNS: AdminTableColumn<Row>[] = [
  { key: 'name', header: '이름', cell: (r) => r.name, sortable: true, sortValue: (r) => r.name },
  {
    key: 'age',
    header: '나이',
    cell: (r) => `${r.age}세`,
    sortable: true,
    sortValue: (r) => r.age,
    align: 'right',
  },
];

function dataRowFirstCells(): (string | null)[] {
  // 첫 행은 헤더(thead의 tr) → 제외.
  return screen
    .getAllByRole('row')
    .slice(1)
    .map((tr) => within(tr).getAllByRole('cell')[0]?.textContent ?? null);
}

describe('AdminTable', () => {
  it('헤더와 셀을 렌더한다', () => {
    render(<AdminTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    expect(screen.getByRole('table')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /이름/ })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: /나이/ })).toBeInTheDocument();
    expect(screen.getByText('Charlie')).toBeInTheDocument();
    expect(screen.getByText('20세')).toBeInTheDocument();
  });

  it('loading 상태를 표시한다', () => {
    render(<AdminTable columns={COLUMNS} rows={[]} rowKey={(r) => r.id} loading />);
    expect(screen.getByText('불러오는 중...')).toBeInTheDocument();
  });

  it('빈 상태 메시지를 표시한다', () => {
    render(<AdminTable columns={COLUMNS} rows={[]} rowKey={(r) => r.id} empty="없음" />);
    expect(screen.getByText('없음')).toBeInTheDocument();
  });

  it('헤더 클릭으로 asc→desc 정렬하고 aria-sort를 갱신한다', () => {
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        rowTestId={(r) => `row-${r.id}`}
      />,
    );
    // 초기: 원본 순서
    expect(dataRowFirstCells()).toEqual(['Charlie', 'Alice', 'Bob']);

    const nameHeader = screen.getByRole('columnheader', { name: /이름/ });
    fireEvent.click(screen.getByTestId('admin-table-sort-name'));
    expect(dataRowFirstCells()).toEqual(['Alice', 'Bob', 'Charlie']);
    expect(nameHeader).toHaveAttribute('aria-sort', 'ascending');

    fireEvent.click(screen.getByTestId('admin-table-sort-name'));
    expect(dataRowFirstCells()).toEqual(['Charlie', 'Bob', 'Alice']);
    expect(nameHeader).toHaveAttribute('aria-sort', 'descending');
  });

  it('숫자 컬럼은 수치 정렬한다(문자열 정렬 아님)', () => {
    render(<AdminTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    fireEvent.click(screen.getByTestId('admin-table-sort-age'));
    // 20,25,30 → Alice, Bob, Charlie
    expect(dataRowFirstCells()).toEqual(['Alice', 'Bob', 'Charlie']);
  });

  it('정렬 불가 컬럼은 헤더 버튼이 없고 aria-sort도 없다', () => {
    const cols: AdminTableColumn<Row>[] = [{ key: 'name', header: '이름', cell: (r) => r.name }];
    render(<AdminTable columns={cols} rows={ROWS} rowKey={(r) => r.id} />);
    expect(screen.queryByTestId('admin-table-sort-name')).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '이름' })).not.toHaveAttribute('aria-sort');
  });

  it('rowTestId로 행을 노출하고 onRowClick을 호출한다', () => {
    let clicked: string | null = null;
    render(
      <AdminTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        rowTestId={(r) => `row-${r.id}`}
        onRowClick={(r) => {
          clicked = r.id;
        }}
      />,
    );
    fireEvent.click(screen.getByTestId('row-2'));
    expect(clicked).toBe('2');
  });
});
