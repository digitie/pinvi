import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TripResponseSchema } from '@pinvi/schemas';
import { TripEditDialog } from '@/components/trips/TripEditDialog';

const trip = TripResponseSchema.parse({
  trip_id: '00000000-0000-4000-8000-000000000001',
  owner_user_id: '00000000-0000-4000-8000-000000000002',
  title: '날짜 여행', description: null, region_hint: null,
  primary_region_code: null, primary_region_source: null,
  start_date: '2026-12-10', end_date: '2026-12-12', visibility: 'private', status: 'draft', version: 2,
  created_at: '2026-11-03T09:00:00+09:00', updated_at: '2026-11-03T09:00:00+09:00',
});

function renderDialog() {
  const onSave = vi.fn();
  render(<TripEditDialog trip={trip} onSave={onSave} onClose={() => undefined} />);
  return onSave;
}

describe('여행 편집 다이얼로그 날짜 검증 (#624)', () => {
  it('종료일이 시작일보다 앞서면 저장하지 않고 종료일 필드에 안내한다', () => {
    const onSave = renderDialog();
    fireEvent.change(screen.getByLabelText('시작일'), { target: { value: '2026-12-15' } });
    fireEvent.change(screen.getByLabelText('종료일'), { target: { value: '2026-12-11' } });
    fireEvent.click(screen.getByTestId('trip-edit-save'));
    expect(onSave).not.toHaveBeenCalled();
    const end = screen.getByLabelText('종료일');
    expect(end).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByText('종료일은 시작일 이후여야 합니다.')).toBeInTheDocument();
    // 날짜를 고치면 오류가 사라지고 저장된다.
    fireEvent.change(end, { target: { value: '2026-12-16' } });
    expect(end).not.toHaveAttribute('aria-invalid', 'true');
    fireEvent.click(screen.getByTestId('trip-edit-save'));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ start_date: '2026-12-15', end_date: '2026-12-16' }));
  });

  it('한쪽 날짜만 비우면 저장하지 않는다', () => {
    const onSave = renderDialog();
    fireEvent.change(screen.getByLabelText('종료일'), { target: { value: '' } });
    fireEvent.click(screen.getByTestId('trip-edit-save'));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByText('시작일과 종료일을 함께 입력하거나 둘 다 비워두세요.')).toBeInTheDocument();
  });

  it('이미 정한 기간을 모두 비우면 아무것도 바뀌지 않는 저장 대신 안내한다', () => {
    const onSave = renderDialog();
    fireEvent.change(screen.getByLabelText('시작일'), { target: { value: '' } });
    fireEvent.change(screen.getByLabelText('종료일'), { target: { value: '' } });
    fireEvent.click(screen.getByTestId('trip-edit-save'));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByLabelText('시작일')).toHaveAttribute('aria-invalid', 'true');
  });
});
