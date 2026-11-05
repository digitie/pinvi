'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { ApiError, telegramApi } from '@pinvi/api-client';
import type { TelegramPreferences, TelegramTarget } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { SettingsSection } from '@/components/app/SettingsSurface';
import { buttonClassName } from '@/components/ui/Button';
import { TelegramNotificationHistory } from './TelegramNotificationHistory';

export function TelegramNotificationPreferences({ targets }: { targets: TelegramTarget[] }) {
  const [value, setValue] = useState<TelegramPreferences | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    void telegramApi(apiClient)
      .preferences()
      .then((result) => {
        if (active) setValue(result);
      })
      .catch((err) => {
        if (active)
          setError(err instanceof ApiError ? err.message : '예약 설정을 불러오지 못했습니다.');
      });
    return () => {
      active = false;
    };
  }, []);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!value || busy) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      setValue(await telegramApi(apiClient).savePreferences(value));
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '예약 설정을 저장하지 못했습니다.');
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <SettingsSection title="예약 알림">
        <p className="mb-3 text-sm text-muted">
          한국 표준시(KST) 기준입니다. 일간 브리프는 전날·당일 일정을, 주간 요약은 앞으로 7일 안에
          시작하는 여행 목록을 보냅니다. 일간·특보 알림은 본인 소유 여행에 연결한 검증된 대상으로만
          보냅니다.
        </p>
        {error && (
          <p role="alert" className="mb-3 rounded-sm bg-error-bg p-3 text-sm text-error-text">
            {error}
          </p>
        )}
        {value ? (
          <form
            onSubmit={(event) => void save(event)}
            className="space-y-3"
            data-testid="telegram-notification-preferences"
          >
            <fieldset disabled={busy} className="space-y-3">
              {(
                [
                  ['daily_enabled', '일간 브리프'],
                  ['weekly_enabled', '주간 여행 요약'],
                  ['weather_enabled', '여행 중 기상 특보 발령·해제'],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="flex min-h-11 items-center gap-2 text-sm text-ink">
                  <input
                    type="checkbox"
                    checked={value[key]}
                    onChange={(event) => {
                      setValue({ ...value, [key]: event.target.checked });
                      setSaved(false);
                    }}
                  />
                  {label}
                </label>
              ))}
              <label className="block text-sm text-ink">
                발송 시각 (KST)
                <input
                  type="time"
                  value={value.send_time}
                  required
                  onChange={(event) => {
                    setValue({ ...value, send_time: event.target.value });
                    setSaved(false);
                  }}
                  className="ml-3 min-h-11 rounded-sm border border-hairline bg-canvas px-3"
                />
              </label>
              <label className="block text-sm text-ink">
                주간 요약 요일
                <select
                  value={value.weekly_day}
                  onChange={(event) => {
                    setValue({ ...value, weekly_day: Number(event.target.value) });
                    setSaved(false);
                  }}
                  className="ml-3 min-h-11 rounded-sm border border-hairline bg-canvas px-3"
                >
                  {['월', '화', '수', '목', '금', '토', '일'].map((day, index) => (
                    <option key={day} value={index}>
                      {day}요일
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm text-ink">
                주간 요약 대상
                <select
                  value={value.weekly_target_id ?? ''}
                  required={value.weekly_enabled}
                  onChange={(event) => {
                    setValue({ ...value, weekly_target_id: event.target.value || null });
                    setSaved(false);
                  }}
                  className="ml-3 min-h-11 max-w-full rounded-sm border border-hairline bg-canvas px-3"
                >
                  <option value="">선택하세요</option>
                  {targets
                    .filter((target) => target.is_enabled && target.last_verified_at)
                    .map((target) => (
                      <option key={target.id} value={target.id}>
                        {target.telegram_label || target.title_snapshot || 'Telegram 대상'}
                      </option>
                    ))}
                </select>
              </label>
              <button type="submit" disabled={busy} className={buttonClassName({ size: 'sm' })}>
                {busy ? '저장 중…' : '예약 설정 저장'}
              </button>
              {saved && (
                <p role="status" className="text-sm text-ink">
                  예약 설정을 저장했습니다.
                </p>
              )}
            </fieldset>
          </form>
        ) : (
          !error && <p className="text-sm text-muted">불러오는 중…</p>
        )}
      </SettingsSection>
      <SettingsSection title="발송 결과">
        <TelegramNotificationHistory targets={targets} />
      </SettingsSection>
    </>
  );
}
