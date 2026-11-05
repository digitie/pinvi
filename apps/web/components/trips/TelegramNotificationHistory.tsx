'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, telegramApi } from '@pinvi/api-client';
import type { TelegramNotification, TelegramTarget } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';

const names: Record<string, string> = {
  itinerary: '일정 보내기',
  planning_error: '예약 알림 실패',
  daily_brief: '일간 브리프',
  weekly_summary: '주간 요약',
  weather_alert: '기상 특보',
};
const statuses: Record<string, string> = {
  pending: '대기 중',
  sent: '전송 완료',
  skipped: '전송 생략',
  failed: '전송 실패',
};

export function TelegramNotificationHistory({
  tripId,
  refreshKey = 0,
  targets = [],
}: {
  tripId?: string;
  refreshKey?: number;
  targets?: TelegramTarget[];
}) {
  const sequence = useRef(0);
  const [rows, setRows] = useState<TelegramNotification[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    const current = ++sequence.current;
    try {
      const result = await telegramApi(apiClient).notifications(tripId);
      if (current !== sequence.current) return;
      setRows(result);
      setError(null);
    } catch (err) {
      if (current !== sequence.current) return;
      setError(err instanceof ApiError ? err.message : '발송 내역을 불러오지 못했습니다.');
    } finally {
      if (current === sequence.current) setLoading(false);
    }
  }, [tripId]);

  useEffect(() => {
    const timer = setTimeout(() => {
      void load();
    }, 0);
    return () => {
      clearTimeout(timer);
      sequence.current += 1;
    };
  }, [load, refreshKey]);
  const pending = rows.some((row) =>
    row.deliveries.some((delivery) => delivery.status === 'pending'),
  );
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => {
      void load();
    }, 5000);
    return () => clearInterval(timer);
  }, [pending, load]);

  return (
    <section
      className="space-y-3"
      aria-label="Telegram 발송 내역"
      data-testid="telegram-notification-history"
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-bold text-ink">최근 발송 내역</h3>
        <button
          type="button"
          onClick={() => void load()}
          className="focus-ring min-h-11 rounded-sm border border-hairline px-3 text-sm text-ink"
        >
          새로고침
        </button>
      </div>
      {error && (
        <p role="alert" className="rounded-sm bg-error-bg p-3 text-sm text-error-text">
          {error}
        </p>
      )}
      {loading ? (
        <p className="text-sm text-muted">불러오는 중…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-muted">발송 내역이 없습니다.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => (
            <li key={row.id} className="space-y-1 rounded-sm border border-hairline p-3 text-sm">
              <p className="font-semibold text-ink">
                {names[row.category] ?? '알림'} ·{' '}
                {new Intl.DateTimeFormat('ko-KR', {
                  timeZone: 'Asia/Seoul',
                  dateStyle: 'short',
                  timeStyle: 'short',
                }).format(new Date(row.created_at))}{' '}
                KST
              </p>
              {row.error_message && (
                <p role="status" className="text-error-text">
                  {row.error_message}
                </p>
              )}
              {row.deliveries.length === 0 && !row.error_message && (
                <p className="text-muted">발송 대상 없음</p>
              )}
              {row.deliveries.map((delivery, index) => (
                <div key={delivery.id} className="text-muted">
                  <p>
                    {targets.find((target) => target.id === delivery.target_id)?.telegram_label ||
                      targets.find((target) => target.id === delivery.target_id)?.title_snapshot ||
                      `대상 ${index + 1}`}{' '}
                    · {statuses[delivery.status]} · {delivery.sent_chunks}/{delivery.total_chunks}개
                    메시지
                  </p>
                  {delivery.error_message && (
                    <p className="text-error-text" role="status">
                      {delivery.error_message}
                    </p>
                  )}
                  {delivery.status === 'pending' && delivery.retry_at && (
                    <p>
                      다음 시도:{' '}
                      {new Intl.DateTimeFormat('ko-KR', {
                        timeZone: 'Asia/Seoul',
                        dateStyle: 'short',
                        timeStyle: 'medium',
                      }).format(new Date(delivery.retry_at))}{' '}
                      KST
                    </p>
                  )}
                </div>
              ))}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
