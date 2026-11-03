import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PoiEditor } from '@/components/trips/PoiEditor';
import { TripViewPoiSchema } from '@pinvi/schemas';

const poi = TripViewPoiSchema.parse({
  poi_id: '00000000-0000-4000-8000-000000000001', feature_id: null,
  sort_order: 'a0', title: '장소', feature: {}, marker_color: null, marker_icon: null,
  feature_resolution_state: 'not_linked', user_note: '보존 메모',
  planned_arrival_at: null, planned_departure_at: null, budget_amount: '12000',
  actual_amount: null, currency: 'KRW', user_url: null, rise_set: null,
  feature_link_broken_at: null, version: 1,
  created_at: '2026-11-03T09:00:00+09:00', updated_at: '2026-11-03T09:00:00+09:00',
});
describe('POI 일자 이동', () => {
  it('대상 일자를 선택해도 메모·비용을 함께 보존한다', () => {
    const onSave = vi.fn();
    render(<PoiEditor poi={poi} currentDayIndex={1}
      dayOptions={[{ day_index: 1, title: null }, { day_index: 2, title: '둘째 날' }]}
      onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('일자 이동'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      day_index: 2, user_note: '보존 메모', budget_amount: 12000,
    }));
  });
  it('일자를 바꾸지 않으면 이동 필드를 보내지 않는다', () => {
    const onSave = vi.fn();
    render(<PoiEditor poi={poi} currentDayIndex={1} onSave={onSave} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave.mock.calls[0]?.[0]).not.toHaveProperty('day_index');
    expect(screen.queryByLabelText('일자 이동')).not.toBeInTheDocument();
  });
});
