import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import type { TelegramPreferences } from '@pinvi/schemas';
import { TelegramNotificationPreferences } from '../components/trips/TelegramNotificationPreferences';

const mocks = vi.hoisted(() => ({
  preferences: vi.fn(),
  savePreferences: vi.fn(),
  notifications: vi.fn(),
}));
vi.mock('@pinvi/api-client', async (original) => ({
  ...(await original<typeof import('@pinvi/api-client')>()),
  telegramApi: () => mocks,
}));
vi.mock('@/lib/api', () => ({ apiClient: {} }));

const initial: TelegramPreferences = {
  weather_enabled: false,
  daily_enabled: false,
  weekly_enabled: false,
  send_time: '08:00',
  weekly_day: 0,
  weekly_target_id: null,
};
beforeEach(() => {
  vi.clearAllMocks();
  mocks.preferences.mockResolvedValue(initial);
  mocks.notifications.mockResolvedValue([]);
});

it('저장 중 입력을 비활성화하여 이전 응답이 새 편집을 덮지 않는다', async () => {
  let complete!: (value: TelegramPreferences) => void;
  mocks.savePreferences.mockImplementation(
    () =>
      new Promise<TelegramPreferences>((resolve) => {
        complete = resolve;
      }),
  );
  const user = userEvent.setup();
  render(<TelegramNotificationPreferences targets={[]} />);
  const daily = await screen.findByLabelText('일간 브리프');
  await user.click(daily);
  await user.click(screen.getByRole('button', { name: '예약 설정 저장' }));
  try {
    expect(daily).toBeDisabled();
    expect(screen.getByLabelText('발송 시각 (KST)')).toBeDisabled();
    expect(screen.getByLabelText('주간 요약 요일')).toBeDisabled();
    await user.click(daily);
    expect(daily).toBeChecked();
  } finally {
    await act(async () => complete({ ...initial, daily_enabled: true }));
  }
  expect(await screen.findByText('예약 설정을 저장했습니다.')).toBeInTheDocument();
  expect(daily).toBeEnabled();
  await user.click(daily);
  expect(daily).not.toBeChecked();
});

it('기상 특보 기본 off와 예약 시각 독립 안내를 저장한다', async () => {
  mocks.savePreferences.mockImplementation(async (value: TelegramPreferences) => value);
  const user = userEvent.setup();
  render(<TelegramNotificationPreferences targets={[]} />);
  const weather = await screen.findByLabelText('여행 중 기상 특보 발표');
  expect(weather).not.toBeChecked();
  expect(screen.getByText(/특보는 예약 시각과 별개로/)).toBeInTheDocument();
  await user.click(weather);
  await user.click(screen.getByRole('button', { name: '예약 설정 저장' }));
  expect(mocks.savePreferences).toHaveBeenCalledWith({ ...initial, weather_enabled: true });
  expect(await screen.findByText('예약 설정을 저장했습니다.')).toBeInTheDocument();
});
