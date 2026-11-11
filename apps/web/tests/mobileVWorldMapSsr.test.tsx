import type { ReactNode } from 'react';
import { renderToString } from 'react-dom/server';
import { expect, it, vi } from 'vitest';

// 서버 렌더가 native 엔진 또는 lazy 웹 엔진을 평가하면 이 sentinel이 즉시 실패한다.
vi.mock('vworld-map-rn', () => {
  throw new Error('native-only engine evaluated on web');
});
vi.mock('vworld-map-web', () => {
  throw new Error('web engine evaluated during SSR');
});
vi.mock('react-native', () => ({
  View: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));
vi.mock('../../mobile/components/ui', () => ({
  Muted: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
}));
import { VWorldMapView } from '../../mobile/components/VWorldMap.web';

it('Expo web SSR는 플랫폼 엔진을 평가하지 않고 접근 가능한 준비 문구만 렌더한다', () => {
  expect(renderToString(<VWorldMapView apiKey="" />)).toContain('지도를 준비하는 중…');
});
