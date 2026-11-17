import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AddPlaceToTripDialog } from '@/components/notice-plans/AddPlaceToTripDialog';

const trips = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn() }));
const pois = vi.hoisted(() => ({ create: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...(await original<typeof import('@pinvi/api-client')>()),
  tripApi: () => trips,
  poiApi: () => pois,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));

const place = {
  feature_id: 'fest-1',
  name: '강릉 겨울바다 축제',
  kind: 'event',
  category: null,
  lon: 128.9,
  lat: 37.8,
  marker_color: 'P-11',
  marker_icon: 'star',
  preferred_date: '2026-12-02',
};

function day(dayIndex: number, date: string, sortOrders: string[]) {
  return {
    day_index: dayIndex,
    date: null,
    effective_date: date,
    pois: sortOrders.map((sort_order) => ({ sort_order })),
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  trips.list.mockResolvedValue([{ trip_id: 'trip-1', title: '강릉 겨울 여행' }]);
  trips.get.mockResolvedValue({
    trip: { trip_id: 'trip-1' },
    days: [day(1, '2026-12-01', ['a0']), day(2, '2026-12-02', ['a0', 'a1'])],
  });
  pois.create.mockResolvedValue({});
});

describe('AddPlaceToTripDialog', () => {
  it('행사 시작일과 같은 일자를 미리 골라 그 일자 끝에 넣는다', async () => {
    render(<AddPlaceToTripDialog place={place} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '강릉 겨울 여행' }));
    const day2 = await screen.findByRole('button', { name: '2일차 · 2026-12-02' });
    await waitFor(() => expect(day2).toHaveAttribute('aria-pressed', 'true'));

    fireEvent.click(screen.getByTestId('add-place-confirm'));
    expect(await screen.findByRole('status')).toHaveTextContent('2일차 · 2026-12-02에 추가했습니다.');
    expect(pois.create).toHaveBeenCalledTimes(1);
    const [tripId, body] = pois.create.mock.calls[0] as [string, { sort_order: string }];
    expect(tripId).toBe('trip-1');
    expect(body).toMatchObject({
      day_index: 2,
      feature_id: 'fest-1',
      source: 'feature',
      feature_snapshot: {
        coord: { lon: 128.9, lat: 37.8 },
        name: '강릉 겨울바다 축제',
        kind: 'event',
        marker_color: 'P-11',
      },
    });
    // 기존 마지막 순서(a1) 뒤에 붙는다.
    expect(body.sort_order > 'a1').toBe(true);
    expect(screen.getByRole('link', { name: '여행 열기' })).toHaveAttribute('href', '/trips/trip-1');
  });

  it('추가 실패는 알리고 다이얼로그를 유지한다', async () => {
    pois.create.mockRejectedValue(new Error('boom'));
    render(<AddPlaceToTripDialog place={{ ...place, preferred_date: null }} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole('button', { name: '강릉 겨울 여행' }));
    const day1 = await screen.findByRole('button', { name: '1일차 · 2026-12-01' });
    await waitFor(() => expect(day1).toHaveAttribute('aria-pressed', 'true'));
    fireEvent.click(screen.getByTestId('add-place-confirm'));
    expect(await screen.findByRole('alert')).toHaveTextContent('장소를 추가하지 못했습니다.');
    expect(screen.getByTestId('add-place-confirm')).toBeInTheDocument();
  });

  it('여행이 없으면 만들라고 안내한다', async () => {
    trips.list.mockResolvedValue([]);
    render(<AddPlaceToTripDialog place={place} onClose={vi.fn()} />);
    expect(await screen.findByText('추가할 여행이 없습니다. 먼저 여행을 만들어 주세요.')).toBeInTheDocument();
    expect(screen.getByTestId('add-place-confirm')).toBeDisabled();
  });
});
