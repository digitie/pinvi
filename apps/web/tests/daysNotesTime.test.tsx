import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TripDayControls } from '@/components/trips/TripDayControls';
import { TripDayHeader } from '@/components/trips/TripDayHeader';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { TripViewPoiSchema } from '@pinvi/schemas';

describe('일자 메모와 KST 표시', () => {
  it('날짜 override가 없는 일자에서도 메모만 저장한다', async () => {
    const save = vi.fn().mockResolvedValue({ ok: true });
    render(<TripDayControls selectedDay={{ day_index: 1, title: null, date: null, note: null, version: 2 }}
      onAdd={vi.fn()} onDelete={vi.fn()} onUpdate={save} />);
    fireEvent.click(screen.getByRole('button', { name: '1일차 설정' }));
    fireEvent.change(screen.getByLabelText('일자 메모'), { target: { value: '예약 확인\n물 챙기기' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(save).toHaveBeenCalledWith(1, expect.objectContaining({ note: '예약 확인\n물 챙기기', date: null }), 2);
    await waitFor(() => expect(screen.queryByTestId('trip-day-title-dialog')).not.toBeInTheDocument());
  });
  it('공유 헤더도 메모를 텍스트로 표시한다', () => {
    render(<TripDayHeader readOnly day={{
      day_index: 1, date: null, effective_date: '2026-11-03', out_of_range: false,
      holidays: [], rise_set: null, rise_set_reference: null, note: '<script>메모</script>',
    }} />);
    expect(screen.getByTestId('trip-day-note')).toHaveTextContent('<script>메모</script>');
    expect(document.querySelector('script')).toBeNull();
  });
  it('도착 예정 시각은 입력 timezone과 관계없이 KST 24시간제로 표시한다', () => {
    const poi = TripViewPoiSchema.parse({
      poi_id: '00000000-0000-4000-8000-000000000001', feature_id: null, sort_order: 'a0',
      title: '장소', feature: {}, marker_color: null, marker_icon: null,
      feature_resolution_state: 'not_linked', user_note: null, planned_arrival_at: '2026-11-03T06:00:00Z',
      planned_departure_at: null, budget_amount: null, actual_amount: null, currency: 'KRW',
      user_url: null, rise_set: null, feature_link_broken_at: null, version: 1,
      created_at: '2026-11-03T00:00:00Z', updated_at: '2026-11-03T00:00:00Z',
    });
    render(<TripPoiList pois={[poi]} />);
    expect(screen.getByText(/15:00/)).toBeInTheDocument();
    expect(screen.queryByText(/오전|오후/)).not.toBeInTheDocument();
  });
});
