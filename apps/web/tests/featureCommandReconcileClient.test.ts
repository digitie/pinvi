import { expect, it, vi } from 'vitest';
import { ApiClient, adminApi } from '@pinvi/api-client';
import { AdminFeatureRequestReconcileSchema } from '@pinvi/schemas';

const rid = '00000000-0000-4000-8000-000000000668';
const key = '00000000-0000-4000-8000-000000000669';

it('원래 명령 키와 별도 확인 사유를 HTTP 경계까지 보존한다', async () => {
  const fetcher = vi.fn(
    async (..._args: unknown[]) =>
      new Response(
        JSON.stringify({
          data: { request_id: rid, status: 'pending', resolution: 'abandoned' },
          meta: { request_id: rid },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
  );
  const client = new ApiClient({ baseUrl: 'http://fixture', fetcher });
  const result = await adminApi(client).reconcileFeatureRequestCommand(rid, {
    expected_command_key: key,
    access_reason: '  실행 기록 확인 사유  ',
  });
  expect(result.resolution).toBe('abandoned');
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(fetcher.mock.calls[0]?.[0]).toBe(
    'http://fixture/admin/feature-requests/' + rid + '/reconcile-map-command',
  );
  expect(JSON.parse(String((fetcher.mock.calls[0]?.[1] as RequestInit | undefined)?.body))).toEqual(
    {
      expected_command_key: key,
      access_reason: '실행 기록 확인 사유',
    },
  );
});

it('세대 키 누락·짧은 확인 사유를 전송 전에 거부한다', () => {
  expect(
    AdminFeatureRequestReconcileSchema.safeParse({ access_reason: '유효한 확인 사유' }).success,
  ).toBe(false);
  expect(
    AdminFeatureRequestReconcileSchema.safeParse({
      expected_command_key: key,
      access_reason: '  짧음 ',
    }).success,
  ).toBe(false);
});

it('알 수 없는 결과는 해제 성공으로 소비하지 않는다', async () => {
  const fetcher = vi.fn(
    async (..._args: unknown[]) =>
      new Response(
        JSON.stringify({
          data: { request_id: rid, status: 'pending', resolution: 'unknown' },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
  );
  const client = new ApiClient({ baseUrl: 'http://fixture', fetcher });
  await expect(
    adminApi(client).reconcileFeatureRequestCommand(rid, {
      expected_command_key: key,
      access_reason: '실행 기록 확인 사유',
    }),
  ).rejects.toThrow();
});
