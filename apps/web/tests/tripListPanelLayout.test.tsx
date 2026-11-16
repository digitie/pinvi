// 일정 패널 일자·장소 행 레이아웃(2026-11-16 소유자 요청 11·12·13).
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { PoiEditor } from '@/components/trips/PoiEditor';
import { TripAttachmentsDisclosure } from '@/components/trips/TripAttachments';
import { TripDayControls } from '@/components/trips/TripDayControls';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { TripViewPoiSchema } from '@pinvi/schemas';

const mocks = vi.hoisted(() => ({
  listPoiAttachments: vi.fn(),
  listDayAttachments: vi.fn(),
  listAttachments: vi.fn(),
}));
vi.mock('@pinvi/api-client', async (original) => ({
  ...(await original<typeof import('@pinvi/api-client')>()),
  tripApi: () => mocks,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));
beforeEach(() => {
  vi.clearAllMocks();
  mocks.listPoiAttachments.mockResolvedValue([]);
  mocks.listDayAttachments.mockResolvedValue([]);
});

const poi = TripViewPoiSchema.parse({
  poi_id: '00000000-0000-4000-8000-000000000001',
  feature_id: null,
  sort_order: 'a0',
  title: '장소',
  feature: {},
  marker_color: null,
  marker_icon: null,
  feature_resolution_state: 'not_linked',
  user_note: '메모',
  planned_arrival_at: null,
  planned_departure_at: null,
  budget_amount: '12000',
  actual_amount: '9000',
  currency: 'KRW',
  user_url: 'https://example.com',
  rise_set: null,
  feature_link_broken_at: null,
  version: 1,
  created_at: '2026-11-03T00:00:00Z',
  updated_at: '2026-11-03T00:00:00Z',
});

const ATTACHMENT = {
  attachment_id: 'a1',
  original_filename: 'ticket.jpg',
  content_type: 'image/jpeg',
  byte_size: 2048,
};

describe('장소 편집기 접힘 항목 (요청 11)', () => {
  it('마커 색·아이콘·도착·출발·예산은 기본 접힘이고 요약만 보인다', () => {
    render(<PoiEditor poi={poi} onSave={vi.fn()} onCancel={vi.fn()} />);
    for (const name of ['마커 색', '아이콘', '도착·출발', '예산·실제 비용']) {
      expect(screen.getByRole('button', { name })).toHaveAttribute('aria-expanded', 'false');
    }
    expect(screen.queryByLabelText('예산')).toBeNull();
    expect(screen.queryByLabelText('도착')).toBeNull();
    expect(screen.queryByLabelText('maki 아이콘')).toBeNull();
    expect(screen.getByTestId('poi-edit-section-budget-summary')).toHaveTextContent(
      '예산 12000 KRW · 실제 9000 KRW',
    );
    expect(screen.getByTestId('poi-edit-section-time-summary')).toHaveTextContent('미정');
    // 메모·링크는 접지 않는다.
    expect(screen.getByLabelText('메모')).toBeVisible();
    expect(screen.getByLabelText('링크')).toBeVisible();
  });

  it('예산 항목은 링크 아래에 있고, 펼치면 입력이 보이며 접어도 값이 저장된다', () => {
    const onSave = vi.fn();
    render(<PoiEditor poi={poi} onSave={onSave} onCancel={vi.fn()} />);
    const link = screen.getByLabelText('링크');
    const budgetToggle = screen.getByRole('button', { name: '예산·실제 비용' });
    expect(
      link.compareDocumentPosition(budgetToggle) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    fireEvent.click(budgetToggle);
    expect(budgetToggle).toHaveAttribute('aria-expanded', 'true');
    fireEvent.change(screen.getByLabelText('예산'), { target: { value: '15000' } });
    fireEvent.click(budgetToggle);
    expect(screen.queryByLabelText('예산')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ budget_amount: 15000, actual_amount: 9000 }),
    );
  });

  it('마커 색 항목을 펼쳐야 색 버튼이 보인다(요약 값은 버튼 이름에 섞이지 않는다)', () => {
    render(<PoiEditor poi={poi} onSave={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole('button', { name: '노랑' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '마커 색' }));
    expect(screen.getByRole('button', { name: '노랑' })).toBeInTheDocument();
  });
});

describe('장소 행 (요청 11·12)', () => {
  it('예산·실제 비용은 메모 아래 마지막 줄에 보인다', async () => {
    render(<TripPoiList pois={[poi]} />);
    const cost = screen.getByTestId('trip-poi-cost');
    expect(cost).toHaveTextContent('예산 12000 KRW');
    expect(cost).toHaveTextContent('실제 9000 KRW');
    const note = screen.getByText('메모');
    expect(note.compareDocumentPosition(cost) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('장소 파일 버튼은 마커 편집 버튼 바로 앞에 있고, 누르면 행 아래에 목록이 펼쳐진다', async () => {
    mocks.listPoiAttachments.mockResolvedValue([ATTACHMENT]);
    render(<TripPoiList pois={[poi]} tripId="trip-1" showInlineAttachments editable />);
    const toggle = screen.getByRole('button', { name: '장소 파일 목록 열기' });
    const edit = screen.getByRole('button', { name: '마커 편집' });
    expect(toggle.parentElement).toBe(edit.parentElement);
    expect(toggle.nextElementSibling).toBe(edit);
    await waitFor(() => expect(toggle).toHaveAttribute('data-attachment-count', '1'));
    expect(screen.queryByText('ticket.jpg')).toBeNull();

    fireEvent.click(toggle);
    expect(screen.getByRole('button', { name: '장소 파일 목록 닫기' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    const panel = screen.getByTestId('trip-attachment-panel');
    expect(within(panel).getByRole('heading', { name: '장소 파일' })).toBeInTheDocument();
    expect(within(panel).getByText('ticket.jpg')).toBeInTheDocument();
    expect(within(panel).getByTestId('attachment-input')).toBeInTheDocument();
  });

  it('인라인 파일을 끄면 파일 버튼도 없다', () => {
    render(<TripPoiList pois={[poi]} tripId="trip-1" editable />);
    expect(screen.queryByTestId('trip-attachment-toggle')).toBeNull();
    expect(mocks.listPoiAttachments).not.toHaveBeenCalled();
  });
});

describe('일자 행 (요청 12·13)', () => {
  it('일자 파일 버튼은 편집 아이콘 옆, 펼친 목록은 호출부가 정한 자리(날짜 아래)에 그린다', async () => {
    mocks.listDayAttachments.mockResolvedValue([
      ATTACHMENT,
      { ...ATTACHMENT, attachment_id: 'a2' },
    ]);
    render(
      <TripAttachmentsDisclosure tripId="trip-1" dayIndex={1} title="1일차 파일">
        {({ trigger, panel }) => (
          <div>
            <TripDayControls
              selectedDay={{ day_index: 1, title: null, date: null }}
              onAdd={vi.fn()}
              onUpdate={vi.fn()}
              onDelete={vi.fn()}
              showAdd={false}
              leading={trigger}
            />
            <span>2026년 11월 5일</span>
            <div data-testid="under-date">{panel}</div>
          </div>
        )}
      </TripAttachmentsDisclosure>,
    );
    const controls = screen.getByTestId('trip-day-controls');
    const toggle = within(controls).getByRole('button', { name: '1일차 파일 목록 열기' });
    expect(toggle.nextElementSibling).toBe(within(controls).getByTestId('trip-day-rename'));
    await waitFor(() => expect(toggle).toHaveAttribute('data-attachment-count', '2'));
    expect(toggle).toHaveTextContent('2');
    expect(screen.getByTestId('under-date')).toBeEmptyDOMElement();

    fireEvent.click(toggle);
    expect(within(screen.getByTestId('under-date')).getAllByText('ticket.jpg')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: '1일차 파일 목록 닫기' }));
    expect(screen.getByTestId('under-date')).toBeEmptyDOMElement();
  });

  it('일자 편집·삭제 버튼은 작아졌지만(28px) 이름이 있다', () => {
    render(
      <TripDayControls
        selectedDay={{ day_index: 2, title: null, date: null }}
        onAdd={vi.fn()}
        onUpdate={vi.fn()}
        onDelete={vi.fn()}
        showAdd={false}
      />,
    );
    const rename = screen.getByRole('button', { name: '2일차 설정' });
    const remove = screen.getByRole('button', { name: '2일차 삭제' });
    for (const button of [rename, remove]) {
      expect(button).toHaveClass('size-7');
      expect(button).not.toHaveClass('size-11');
    }
  });
});
