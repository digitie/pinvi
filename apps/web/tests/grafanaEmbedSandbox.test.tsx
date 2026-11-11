import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import AdminGrafanaPage from '@/app/(admin)/admin/grafana/page';

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: 'ok', status_code: 200, message: 'ok' }),
    })),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
describe('Grafana 프레임 격리', () => {
  it('같은 origin에서는 sandbox를 제거할 수 있는 스크립트 권한을 주지 않는다', async () => {
    vi.stubEnv('NEXT_PUBLIC_GRAFANA_URL', window.location.origin);
    render(<AdminGrafanaPage />);
    const frame = await screen.findByTestId('admin-grafana-frame');
    expect(frame.getAttribute('sandbox')?.split(' ')).not.toContain('allow-scripts');
    expect(frame.getAttribute('sandbox')?.split(' ')).not.toContain('allow-same-origin');
    expect(screen.getByRole('alert')).toHaveTextContent('별도 origin');
  });
  it('다른 origin의 Grafana는 기존 쿠키/스크립트 동작을 유지한다', async () => {
    vi.stubEnv('NEXT_PUBLIC_GRAFANA_URL', 'https://grafana.example.test');
    render(<AdminGrafanaPage />);
    const frame = await screen.findByTestId('admin-grafana-frame');
    expect(frame.getAttribute('sandbox')?.split(' ')).toEqual(
      expect.arrayContaining(['allow-scripts', 'allow-same-origin']),
    );
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
