import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { PoiEditor } from '@/components/trips/PoiEditor';
import { MARKER_ICON_OPTIONS } from '@/lib/makiIcons';
import { hasBundledIcon } from '@/lib/markerIconGlyphs';
import { MARKER_PALETTE } from '@pinvi/design-tokens';
import { TripViewPoiSchema } from '@pinvi/schemas';

/** 아이콘·마커 색은 접힌 편집 항목 안에 있다(요청 11) — 펼친다. */
function openSection(name: '아이콘' | '마커 색') {
  fireEvent.click(screen.getByRole('button', { name }));
}

const basePoi = {
  poi_id: '00000000-0000-4000-8000-000000000001', feature_id: null,
  sort_order: 'a0', title: '장소', feature: {}, marker_color: 'P-03',
  feature_resolution_state: 'not_linked', user_note: null,
  planned_arrival_at: null, planned_departure_at: null, budget_amount: null,
  actual_amount: null, currency: 'KRW', user_url: null, rise_set: null,
  feature_link_broken_at: null, version: 1,
  created_at: '2026-11-03T09:00:00+09:00', updated_at: '2026-11-03T09:00:00+09:00',
};

function hexToRgb(hex: string): string {
  const value = Number.parseInt(hex.slice(1), 16);
  return `rgb(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255})`;
}

describe('POI 마커 아이콘 고르기(텍스트 입력 대신 아이콘 칩)', () => {
  it('아이콘 이름 입력칸 없이 칩 목록을 보여 주고, 고른 칩을 custom_marker_icon으로 저장한다', () => {
    const onSave = vi.fn();
    const poi = TripViewPoiSchema.parse({ ...basePoi, marker_icon: 'marker' });
    render(<PoiEditor poi={poi} onSave={onSave} onCancel={vi.fn()} />);
    // 접힌 머리글의 요약은 고른 아이콘 이름이다.
    expect(screen.getByTestId('poi-edit-section-icon-summary')).toHaveTextContent('기본 핀');
    openSection('아이콘');
    expect(screen.queryByLabelText('maki 아이콘')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: /아이콘/ })).not.toBeInTheDocument();
    const group = screen.getByRole('group', { name: '마커 아이콘' });
    expect(group.querySelectorAll('[data-marker-icon-option]')).toHaveLength(
      MARKER_ICON_OPTIONS.length,
    );
    expect(screen.getByRole('button', { name: '기본 핀' })).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(screen.getByRole('button', { name: '카페' }));
    expect(screen.getByRole('button', { name: '카페' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('poi-edit-section-icon-summary')).toHaveTextContent('카페');
    expect(screen.getByRole('button', { name: '기본 핀' })).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ custom_marker_icon: 'cafe', custom_marker_color: 'P-03' }),
    );
  });

  it('목록에 없는 지금 아이콘(카테고리 값)은 맨 앞 칩으로 남아 저장해도 잃지 않는다', () => {
    const onSave = vi.fn();
    const poi = TripViewPoiSchema.parse({ ...basePoi, marker_icon: 'religious-christian' });
    render(<PoiEditor poi={poi} onSave={onSave} onCancel={vi.fn()} />);
    openSection('아이콘');
    const current = screen.getByRole('button', { name: '지금 아이콘' });
    expect(current).toHaveAttribute('aria-pressed', 'true');
    expect(current).toHaveAttribute('data-marker-icon-option', 'religious-christian');
    fireEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ custom_marker_icon: 'religious-christian' }),
    );
  });

  it('고르기 목록의 아이콘은 모두 앱에 묶인 그림이라 외부 SVG를 받지 않는다', () => {
    expect(MARKER_ICON_OPTIONS.filter((option) => !hasBundledIcon(option.icon))).toEqual([]);
    expect(new Set(MARKER_ICON_OPTIONS.map((option) => option.icon)).size).toBe(
      MARKER_ICON_OPTIONS.length,
    );
    const poi = TripViewPoiSchema.parse({ ...basePoi, marker_icon: 'marker' });
    const { container } = render(<PoiEditor poi={poi} onSave={vi.fn()} onCancel={vi.fn()} />);
    openSection('아이콘');
    expect(container.querySelectorAll('[data-marker-icon-option] img')).toHaveLength(0);
    expect(container.querySelectorAll('[data-marker-icon-option] svg')).toHaveLength(
      MARKER_ICON_OPTIONS.length,
    );
  });

  it('아이콘 칩은 44px 터치 타깃이고 미리보기 원은 고른 마커 색을 따른다', () => {
    const poi = TripViewPoiSchema.parse({ ...basePoi, marker_icon: 'marker' });
    render(<PoiEditor poi={poi} onSave={vi.fn()} onCancel={vi.fn()} />);
    openSection('아이콘');
    openSection('마커 색');
    const chip = screen.getByRole('button', { name: '숙소' });
    expect(chip.className).toContain('size-11');
    const preview = chip.querySelector('span') as HTMLElement;
    expect(preview.style.backgroundColor).toBe(hexToRgb(MARKER_PALETTE['P-03'].hex));
    fireEvent.click(screen.getByRole('button', { name: MARKER_PALETTE['P-07'].name }));
    expect(preview.style.backgroundColor).toBe(hexToRgb(MARKER_PALETTE['P-07'].hex));
  });
});
