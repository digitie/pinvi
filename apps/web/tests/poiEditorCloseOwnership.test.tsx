import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { TripPoiList } from '@/components/trips/TripPoiList';
import { TripViewPoiSchema } from '@pinvi/schemas';

const poi = TripViewPoiSchema.parse({
  poi_id: '00000000-0000-4000-8000-000000000001', feature_id: null, sort_order: 'a0',
  title: '장소', feature: {}, marker_color: null, marker_icon: null,
  feature_resolution_state: 'not_linked', user_note: null, planned_arrival_at: null,
  planned_departure_at: null, budget_amount: null, actual_amount: null, currency: 'KRW',
  user_url: null, rise_set: null, feature_link_broken_at: null, version: 1,
  created_at: '2026-11-03T00:00:00Z', updated_at: '2026-11-03T00:00:00Z',
});

// #699: 저장 뒤 재조회까지 기다리는 동안 다른 장소 편집기를 열 수 있다. 제어 모드에서 목록이 비동기 저장
// 결과로 편집기를 닫으면(onEditToggle(null)) 그 사이 연 엉뚱한 편집기가 닫힌다 — 닫기는 부모 몫이다.
describe('편집기 닫기 소유권 (#699)', () => {
  it('제어 모드 비동기 저장 성공은 목록이 편집기를 닫지 않는다', async () => {
    const onEditToggle = vi.fn();
    const onEditPoi = vi.fn(() => Promise.resolve(true));
    render(
      <TripPoiList
        pois={[poi]}
        editable
        onEditPoi={onEditPoi}
        editingPoiId={poi.poi_id}
        onEditToggle={onEditToggle}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(onEditPoi).toHaveBeenCalledTimes(1));
    await Promise.resolve();
    await Promise.resolve();
    expect(onEditToggle).not.toHaveBeenCalledWith(null);
  });

  it('비제어 모드는 저장 성공 뒤 스스로 닫는다', async () => {
    const onEditPoi = vi.fn(() => Promise.resolve(true));
    render(<TripPoiList pois={[poi]} editable onEditPoi={onEditPoi} />);
    fireEvent.click(screen.getByRole('button', { name: '마커 편집' }));
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(screen.queryByTestId('poi-editor')).toBeNull());
  });
});
