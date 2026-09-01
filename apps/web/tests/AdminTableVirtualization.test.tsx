import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

/**
 * `virtualized` prop과 **실제 DOM 윈도잉**의 분리를 잠근다(T-356).
 *
 * pinvi에서 `virtualized`는 "높이를 제한하고 세로로 스크롤한다"는 뜻이고, 윈도잉은 행수가
 * 임계를 넘을 때만 켠다(1행 e2e mock 안정성). 이 둘을 한 플래그로 묶었더니 3행짜리 로그 표에서
 * sticky 헤더와 maxHeight가 함께 사라지는 회귀가 났다 — `e2e/admin-table.e2e.ts`가 정확히 3행으로
 * sticky를 잠그고 있고, 로그 필터를 좁게 걸면 표 내부 스크롤이 페이지 전체 스크롤로 튄다.
 * Playwright는 N150 전용이라(ADR-051) 이 계약을 단위 테스트로도 잠가 둔다.
 */
interface Row {
  id: string;
  name: string;
}

const COLUMNS: AdminTableColumn<Row>[] = [
  { key: 'name', header: '이름', cell: (r) => r.name, sortable: true, sortValue: (r) => r.name },
];

function makeRows(count: number): Row[] {
  return Array.from({ length: count }, (_, i) => ({
    id: String(i),
    name: `row-${String(i).padStart(3, '0')}`,
  }));
}

function renderTable(rowCount: number) {
  return render(
    <AdminTable
      columns={COLUMNS}
      rows={makeRows(rowCount)}
      rowKey={(r) => r.id}
      virtualized
      maxHeight="70dvh"
    />,
  );
}

describe('AdminTable — virtualized prop vs 실제 윈도잉', () => {
  it('임계 미만 행수에서도 sticky 헤더를 유지한다', () => {
    const { container } = renderTable(3);
    const thead = container.querySelector('thead');
    expect(thead).not.toBeNull();
    expect(thead!.className).toContain('sticky');
  });

  it('임계 초과 행수에서도 sticky 헤더를 유지한다', () => {
    const { container } = renderTable(40);
    const header = container.querySelector('[data-slot="table-header"], thead');
    expect(header).not.toBeNull();
    expect(header!.className).toContain('sticky');
  });

  it('임계 미만 행수에서도 maxHeight를 유지한다', () => {
    renderTable(3);
    const scroll = screen.getByTestId('admin-table-scroll');
    expect(scroll.style.maxHeight).toBe('70dvh');
  });

  it('임계 초과 행수에서도 maxHeight를 유지한다', () => {
    renderTable(40);
    const scroll = screen.getByTestId('admin-table-scroll');
    expect(scroll.style.maxHeight).toBe('70dvh');
  });

  it('virtualized가 아니면 높이를 제한하지 않는다', () => {
    render(<AdminTable columns={COLUMNS} rows={makeRows(3)} rowKey={(r) => r.id} />);
    const scroll = screen.getByTestId('admin-table-scroll');
    expect(scroll.style.maxHeight).toBe('');
  });

  it('admin-table-scroll이 실제 스크롤 컨테이너다 (e2e가 이 요소를 직접 scrollTo 한다)', () => {
    const { container } = renderTable(3);
    const scroll = screen.getByTestId('admin-table-scroll');
    // 래퍼가 아니라 Table/Virtualized 컨테이너 자신이어야 한다.
    expect(scroll.getAttribute('data-slot')).toBe('table-container');
    expect(scroll.className).toContain('overflow-auto');
    expect(container.querySelector('[data-testid="admin-table-scroll"] table')).not.toBeNull();
  });
});

describe('AdminTable — 클릭 가능한 행에만 hover 배경', () => {
  it('onRowClick이 없으면 행에 hover 배경을 주지 않는다', () => {
    const { container } = render(
      <AdminTable columns={COLUMNS} rows={makeRows(2)} rowKey={(r) => r.id} />,
    );
    const row = container.querySelector('tbody tr');
    expect(row).not.toBeNull();
    expect(row!.hasAttribute('data-clickable')).toBe(false);
  });

  it('onRowClick이 있으면 클릭 가능 표식을 붙인다', () => {
    const { container } = render(
      <AdminTable
        columns={COLUMNS}
        rows={makeRows(2)}
        rowKey={(r) => r.id}
        onRowClick={() => {}}
      />,
    );
    const row = container.querySelector('tbody tr');
    expect(row).not.toBeNull();
    expect(row!.hasAttribute('data-clickable')).toBe(true);
    expect(row!.getAttribute('tabindex')).toBe('0');
  });
});

describe('AdminTable — 헤더 접근성', () => {
  it('모든 th가 scope="col"을 갖는다', () => {
    const { container } = render(
      <AdminTable columns={COLUMNS} rows={makeRows(2)} rowKey={(r) => r.id} />,
    );
    const heads = Array.from(container.querySelectorAll('th'));
    expect(heads.length).toBeGreaterThan(0);
    for (const th of heads) expect(th.getAttribute('scope')).toBe('col');
  });

  it('ariaLabel을 주면 표에 접근성 이름이 붙는다', () => {
    render(
      <AdminTable
        columns={COLUMNS}
        rows={makeRows(2)}
        rowKey={(r) => r.id}
        ariaLabel="API 호출 목록"
      />,
    );
    expect(screen.getByRole('table', { name: 'API 호출 목록' })).toBeInTheDocument();
  });
});
