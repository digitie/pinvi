import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';

/**
 * `AdminPage`의 렌더 계약을 잠근다(T-357).
 *
 * `Section`과 `FilterBar`는 KTM `SectionCard`/`FilterBar`로 **위임**된다. 소비처가 60곳이라
 * 위임 대상이 바뀌면 그 전부의 시각·구조가 한 번에 움직이는데, 이 저장소에는
 * `@/components/admin/AdminPage`를 렌더하는 테스트가 하나도 없었다 — 실제로 T-357 리뷰가
 * 지적한 시각 델타를 어느 게이트도 잡지 못했다.
 *
 * 픽셀을 잠그지는 않는다(그건 스크린샷 테스트의 몫). 대신 **깨지면 20~60쪽이 동시에 잘못되는
 * 구조 계약**만 본다: 제목이 heading으로 나오는가, 표가 카드 안에서 flush 되는가, 높이를 제한한
 * 표는 반대로 프레임을 지키는가.
 */
interface Row {
  id: string;
  name: string;
}

const ROWS: Row[] = [{ id: '1', name: 'Alice' }];
const COLUMNS: AdminTableColumn<Row>[] = [{ key: 'name', header: '이름', cell: (r) => r.name }];

function tableContainer() {
  return screen.getByTestId('admin-table-scroll');
}

describe('AdminPage.Section 계약', () => {
  it('제목을 heading으로 렌더한다 (문서 개요 유지)', () => {
    render(<Section title="운영 작업">내용</Section>);
    expect(screen.getByRole('heading', { name: '운영 작업' })).toBeInTheDocument();
  });

  it('카드 컨테이너를 렌더한다 (표 flush 규칙이 걸리는 지점)', () => {
    const { container } = render(<Section title="제목">내용</Section>);
    const card = container.querySelector('[data-slot="card"]');
    expect(card, 'Section이 Card로 위임되지 않으면 안쪽 표의 flush 규칙이 죽는다').not.toBeNull();
    expect(card!.className).toContain('group/card');
  });

  it('일반 표는 카드 안에서 flush 된다 (containment 1층)', () => {
    render(
      <Section title="목록">
        <AdminTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />
      </Section>,
    );
    // 카드가 프레임을 제공하므로 표는 자기 테두리를 버린다.
    expect(tableContainer().className).toContain('group-data-[slot=card]/card:border-0');
  });

  it('높이를 제한한 표는 카드 안에서도 프레임을 지킨다 (스크롤 경계 가시성)', () => {
    render(
      <Section title="로그">
        <AdminTable
          columns={COLUMNS}
          rows={ROWS}
          rowKey={(r) => r.id}
          virtualized
          maxHeight="40dvh"
        />
      </Section>,
    );
    const cls = tableContainer().className;
    // flush를 되돌리는 재선언이 있어야 한다 — 없으면 내용이 잘리는 지점이 보이지 않는다.
    expect(cls).toContain('group-data-[slot=card]/card:border');
    expect(cls).toContain('group-data-[slot=card]/card:rounded-panel');
    expect(tableContainer().style.maxHeight).toBe('40dvh');
  });
});

describe('AdminPage.FilterBar 계약', () => {
  it('KTM FilterBar로 위임된다 (프레임 없음 + items-end)', () => {
    const { container } = render(
      <FilterBar>
        <button type="button">조회</button>
      </FilterBar>,
    );
    const bar = container.querySelector('[data-slot="filter-bar"]');
    expect(bar).not.toBeNull();
    // `items-end`가 아니면 라벨 있는 FilterField와 버튼의 밑선이 어긋난다.
    expect(bar!.className).toContain('items-end');
  });
});

describe('AdminPage 셸 계약', () => {
  it('제목을 h1으로, 설명과 액션을 함께 렌더한다', () => {
    render(
      <AdminPage title="사용자" description="계정 관리" actions={<button type="button">생성</button>}>
        본문
      </AdminPage>,
    );
    expect(screen.getByRole('heading', { level: 1, name: '사용자' })).toBeInTheDocument();
    expect(screen.getByText('계정 관리')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '생성' })).toBeInTheDocument();
  });
});
