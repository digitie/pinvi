import type { ReactNode } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MarkerItem, VWorldMapViewProps } from 'vworld-map-core';

/** 네이티브 어댑터가 `vworld-map-rn`에 무엇을 넘기는지 본다(패키지는 mock — 네이티브 모듈을 jsdom에서 띄우지 않는다). */
const rn = vi.hoisted(() => ({ props: null as VWorldMapViewProps | null }));

vi.mock('vworld-map-rn', () => ({
  VWorldMapView: (props: VWorldMapViewProps) => {
    rn.props = props;
    return <section data-testid="rn-map">{props.children}</section>;
  },
  Marker: (props: {
    id: string;
    lngLat: [number, number];
    ariaLabel?: string;
    onPress?: () => void;
    children?: ReactNode;
  }) => (
    <button
      type="button"
      data-rn-marker={props.id}
      data-lnglat={props.lngLat.join(',')}
      aria-label={props.ariaLabel}
      onClick={props.onPress}
    >
      {props.children}
    </button>
  ),
}));

const { VWorldMapView } = await import('../components/VWorldMap.native');

beforeEach(() => {
  rn.props = null;
});

describe('VWorldMap.native — vworld-map-rn 어댑터', () => {
  it('기본 마커는 패키지 markers로, 이름·작은 원 마커는 패키지 Marker 자식으로 그린다', () => {
    const onFeaturePress = vi.fn();
    render(
      <VWorldMapView
        apiKey="k"
        initialCenter={[127, 37.5]}
        initialZoom={12}
        onFeaturePress={onFeaturePress}
        markers={[
          { id: 'me', coordinate: [127, 37.5], color: '#1E88E5' },
          { id: 'poi:a', coordinate: [127.1, 37.6], color: '#E53935', label: '경포대' },
          { id: 'transport:fuel_station:f', coordinate: [127.2, 37.7], compact: true },
        ]}
      />,
    );
    expect(rn.props?.markers?.map((m: MarkerItem) => m.id)).toEqual(['me']);
    expect(rn.props?.initialCenter).toEqual([127, 37.5]);

    const poi = screen.getByRole('button', { name: '경포대' });
    expect(poi.getAttribute('data-rn-marker')).toBe('poi:a');
    expect(poi.getAttribute('data-lnglat')).toBe('127.1,37.6');
    expect(poi.textContent).toContain('경포대');

    fireEvent.click(poi);
    expect(onFeaturePress).toHaveBeenCalledWith(expect.objectContaining({ id: 'poi:a' }));
    expect(document.querySelector('[data-rn-marker="transport:fuel_station:f"]')).not.toBeNull();
  });
});
