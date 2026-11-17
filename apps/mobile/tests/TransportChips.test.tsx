import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { MapCamera } from '../lib/cameraBbox';

const requests = vi.hoisted(() => ({ paths: [] as string[] }));

vi.mock('../lib/api', () => ({
  apiClient: {
    request: async (path: string) => {
      requests.paths.push(path);
      if (path === '/transport/status') {
        return {
          enabled: true,
          layers: [
            { layer: 'fuel_station', available: true },
            { layer: 'highway_incident', available: true },
          ],
        };
      }
      return { layers: [] };
    },
  },
}));

const { TransportChips, useMobileTransport } = await import('../components/TransportLayers');

const CAMERA: MapCamera = {
  center: [127, 37.5],
  zoom: 12,
  bounds: { sw: [126.9, 37.4], ne: [127.1, 37.6] },
};

function Harness({ camera }: { camera: MapCamera | null }) {
  const state = useMobileTransport(camera);
  return <TransportChips state={state} />;
}

function renderHarness(camera: MapCamera | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness camera={camera} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  requests.paths = [];
});

describe('탐색 지도 교통 칩', () => {
  it('기능이 켜져 있으면 주유소·교통 돌발 칩을 그리고, 켠 레이어만 화면 범위로 조회한다', async () => {
    renderHarness(CAMERA);
    const fuel = await screen.findByRole('button', { name: '주유소' });
    expect(screen.getByRole('button', { name: '교통 돌발' })).toBeTruthy();
    // 켜기 전에는 마커를 조회하지 않는다.
    expect(requests.paths.some((p) => p.startsWith('/transport/markers'))).toBe(false);

    fireEvent.click(fuel);
    await waitFor(() =>
      expect(requests.paths.find((p) => p.startsWith('/transport/markers-in-bounds'))).toContain(
        'layers=fuel_station',
      ),
    );
  });
});
