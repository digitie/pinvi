import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { TelegramNotificationHistory } from '../components/trips/TelegramNotificationHistory';

const mocks = vi.hoisted(() => ({ notifications: vi.fn() }));
vi.mock('@pinvi/api-client', async (original) => ({
  ...(await original<typeof import('@pinvi/api-client')>()),
  telegramApi: () => mocks,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));

it('예약 실패를 수신자 없는 정상 빈 목록으로 표시하지 않는다', async () => {
  mocks.notifications.mockResolvedValue([
    {
      id: '00000000-0000-4000-8000-000000000001',
      category: 'planning_error',
      trip_ids: [],
      created_at: '2026-11-05T00:00:00Z',
      error_code: 'TELEGRAM_MESSAGE_TOO_LARGE',
      error_message: '일정이 너무 길어 예약 알림을 만들지 못했습니다.',
      deliveries: [],
    },
  ]);
  render(<TelegramNotificationHistory />);
  expect(await screen.findByText('일정이 너무 길어 예약 알림을 만들지 못했습니다.')).toBeVisible();
  expect(screen.queryByText('발송 대상 없음')).not.toBeInTheDocument();
});
