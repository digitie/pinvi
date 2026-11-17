import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { MapPin } from '../components/MapPin';

describe('MapPin — 원 안 아이콘·이름 옆 날씨', () => {
  it('아이콘 고르기 목록의 이름은 앱에 묶인 lucide 그림(웹과 같은 이름)을 흰색으로 그린다', () => {
    const { container } = render(<MapPin color="#E53935" label="카페" icon="cafe" />);
    const glyph = container.querySelector('[data-lucide]');
    expect(glyph?.getAttribute('data-lucide')).toBe('Coffee');
    expect(glyph?.getAttribute('data-color')).toBe('#ffffff');
    expect(container.querySelector('[data-svg-uri]')).toBeNull();
  });

  it('옛 별칭은 바꿔 그리고, 목록 밖 maki 이름은 maki SVG를 흰색으로 받는다', () => {
    const alias = render(<MapPin color="#000" label="전망" icon="camera" />);
    expect(alias.container.querySelector('[data-lucide]')?.getAttribute('data-lucide')).toBe(
      'Camera',
    );
    alias.unmount();
    const { container } = render(<MapPin color="#000" label="도서관" icon="library" />);
    const svg = container.querySelector('[data-svg-uri]');
    expect(svg?.getAttribute('data-svg-uri')).toBe(
      'https://unpkg.com/@mapbox/maki@8.0.0/icons/library.svg',
    );
    expect(svg?.getAttribute('data-fill')).toBe('#ffffff');
  });

  it('날씨를 알면 이름 옆에 상태 그림(색 의미 포함), 모르면 그리지 않는다', () => {
    const rain = render(
      <MapPin color="#000" label="경포대" weather={{ condition: 'rain', night: false }} />,
    );
    const glyph = rain.getByTestId('map-pin-weather').querySelector('[data-lucide]');
    expect(glyph?.getAttribute('data-lucide')).toBe('CloudRain');
    expect(glyph?.getAttribute('data-color')).toBe('#ff385c');
    rain.unmount();
    const night = render(
      <MapPin color="#000" label="경포대" weather={{ condition: 'clear', night: true }} />,
    );
    expect(
      night
        .getByTestId('map-pin-weather')
        .querySelector('[data-lucide]')
        ?.getAttribute('data-lucide'),
    ).toBe('Moon');
    night.unmount();
    const unknown = render(<MapPin color="#000" label="경포대" weather={null} />);
    expect(unknown.queryByTestId('map-pin-weather')).toBeNull();
  });
});
