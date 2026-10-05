import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AdminEtlSummarySchema } from '@pinvi/schemas';
import { beforeEach, expect, test, vi } from 'vitest';
import AdminEtlPage from '../app/(admin)/admin/etl/page';
import AdminLoginPage from '../app/(admin)/admin/login/page';

const mocks = vi.hoisted(() => ({
  summary: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  push: vi.fn(),
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mocks.push }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@pinvi/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@pinvi/api-client')>()),
  adminApi: () => ({
    getEtlSummary: mocks.summary,
    listProviderImportJobs: async () => ({ items: [] }),
  }),
  authApi: () => ({ login: mocks.login, logout: mocks.logout }),
}));
function host(child: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { client, ...render(<QueryClientProvider client={client}>{child}</QueryClientProvider>) };
}
function snapshot(status: 'ok' | 'degraded', runId = 'old-active') {
  return AdminEtlSummarySchema.parse({
    generated_at: '2026-10-05T00:00:00Z',
    pinvi: {
      status,
      message: status === 'ok' ? null : 'Dagster 연결 실패',
      checked_at: '2026-10-05T00:00:00Z',
      repositories:
        status === 'ok'
          ? [
              {
                name: '__repository__',
                location_name: 'pinvi.etl.definitions',
                jobs: [{ name: 'pinvi_email_outbox_job' }],
                schedules: [
                  {
                    name: 'email',
                    job_name: 'pinvi_email_outbox_job',
                    status: 'RUNNING',
                    cron_schedule: '*/15 * * * *',
                    execution_timezone: 'Asia/Seoul',
                    last_tick: { status: 'SUCCESS', timestamp: 1780000000 },
                  },
                ],
              },
            ]
          : [],
      recent_runs:
        status === 'ok'
          ? [
              {
                run_id: runId,
                job_name: 'pinvi_email_outbox_job',
                status: 'STARTED',
                start_time: 1780000000,
                end_time: null,
              },
            ]
          : [],
    },
    kor_travel_map: { status: 'down', dagster_status: 'unavailable' },
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  mocks.logout.mockResolvedValue(undefined);
});

test('semantic outage keeps the last good scoped run and manual retry replaces it', async () => {
  mocks.summary
    .mockResolvedValueOnce(snapshot('ok'))
    .mockResolvedValueOnce(snapshot('degraded'))
    .mockResolvedValueOnce(snapshot('ok', 'recovered-run'));
  const { container } = host(<AdminEtlPage />);
  await waitFor(() =>
    expect(container.querySelector('[data-slot="dagster-operations"]')).toHaveTextContent(
      'old-active',
    ),
  );
  fireEvent.click(screen.getByTestId('admin-etl-refresh'));
  await waitFor(() => expect(screen.getAllByText(/Dagster 연결 실패/).length).toBeGreaterThan(0));
  expect(container.querySelector('[data-slot="dagster-operations"]')).toHaveTextContent(
    'old-active',
  );
  expect(container.querySelector('[data-slot="dagster-operations"]')).not.toHaveTextContent(
    'recovered-run',
  );
  fireEvent.click(screen.getByTestId('admin-etl-refresh'));
  await waitFor(() =>
    expect(container.querySelector('[data-slot="dagster-operations"]')).toHaveTextContent(
      'recovered-run',
    ),
  );
  expect(mocks.summary.mock.calls[0]![0]?.signal).toBeInstanceOf(AbortSignal);
});

test('shared login preserves PinVi validation/focus and clears submitted password', async () => {
  const { container } = host(<AdminLoginPage />);
  const email = container.querySelector<HTMLInputElement>('[name=username]')!;
  const password = container.querySelector<HTMLInputElement>('[name=password]')!;
  fireEvent.change(email, { target: { value: 'not-an-email' } });
  fireEvent.change(password, { target: { value: 'invalid-password' } });
  fireEvent.submit(screen.getByTestId('admin-login-form'));
  await waitFor(() => expect(email).toHaveAttribute('aria-invalid', 'true'));
  expect(email).toHaveFocus();
  await waitFor(() => expect(password.value).toBe(''));
  expect(mocks.login).not.toHaveBeenCalled();
});

test('non-admin login is logged out and cannot navigate into admin', async () => {
  mocks.login.mockResolvedValue({ roles: ['user'] });
  const { container, client } = host(<AdminLoginPage />);
  client.setQueryData(['admin', 'me'], { roles: ['admin'] });
  fireEvent.change(container.querySelector('[name=username]')!, {
    target: { value: 'user@example.com' },
  });
  fireEvent.change(container.querySelector('[name=password]')!, {
    target: { value: 'valid-password' },
  });
  fireEvent.submit(screen.getByTestId('admin-login-form'));
  await waitFor(() => expect(mocks.logout).toHaveBeenCalledOnce());
  await waitFor(() => expect(client.getQueryData(['admin', 'me'])).toBeUndefined());
  expect(mocks.push).not.toHaveBeenCalled();
});
