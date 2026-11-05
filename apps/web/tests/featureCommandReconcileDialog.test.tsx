import React from 'react';
import { expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import AdminFeatureRequestsPage from '@/app/(admin)/admin/feature-requests/page';

const state = vi.hoisted(() => ({
  rows: [] as unknown[],
  reconcile: vi.fn().mockResolvedValue({ resolution: 'pending' }),
}));
vi.mock('@/components/admin/AdminPage', () => ({
  AdminPage: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));
vi.mock('@pinvi/api-client', async (load) => ({
  ...await load<typeof import('@pinvi/api-client')>(),
  adminApi: () => ({
    listFeatureRequests: async () => ({ items: state.rows, total: 1, page: 1, limit: 20 }),
    reconcileFeatureRequestCommand: state.reconcile,
  }),
}));

it('확인창 열린 뒤 다른 명령으로 재조회되어도 원래 키와 사유만 전송한다', async () => {
  const rid = '00000000-0000-4000-8000-000000000668';
  const k1 = '00000000-0000-4000-8000-000000000669';
  const original = {
    request_id: rid, requester_user_id: rid, type: 'correction', kind: 'place',
    name: '명령 확인 검증', coord: { lon: 127, lat: 37 }, categories: [],
    status: 'pending', created_at: '2026-11-05T00:00:00Z',
    kor_travel_map_ref: { dispatch: {
      actor: 'pinvi-admin', command_key: rid,
      input: { access_reason: '원래 사유', name: '원래 이름' },
    } },
  };
  state.rows = [original];
  state.reconcile.mockClear();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><AdminFeatureRequestsPage /></QueryClientProvider>);
  fireEvent.click(await screen.findByTestId('admin-fr-review-' + rid));
  fireEvent.change(screen.getByTestId('admin-fr-resolution-reason'), { target: { value: '원래 명령 확인 사유' } });
  fireEvent.click(screen.getByTestId('admin-fr-reconcile-command'));
  expect(await screen.findByTestId('admin-fr-reconcile-confirm')).toHaveTextContent('원래 명령 확인 사유');
  state.rows = [{
    ...original,
    kor_travel_map_ref: { dispatch: {
      ...original.kor_travel_map_ref.dispatch, command_key: k1,
      input: { access_reason: '새 사유', name: '새 이름' },
    } },
  }];
  await act(async () => {
    await client.invalidateQueries({ queryKey: queryKeys.admin.featureRequestsAll() });
  });
  await waitFor(() => expect(screen.getByTestId('admin-fr-name')).toHaveValue('새 이름'));
  fireEvent.click(screen.getByTestId('admin-fr-reconcile-confirm-confirm'));
  await waitFor(() => expect(state.reconcile).toHaveBeenCalledTimes(1));
  expect(state.reconcile).toHaveBeenCalledWith(rid, {
    expected_command_key: rid, access_reason: '원래 명령 확인 사유',
  });
  client.clear();
});
