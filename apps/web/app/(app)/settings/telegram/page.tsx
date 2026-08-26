'use client';

import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { BadgeCheck, Loader2, Send, Star, Trash2 } from 'lucide-react';
import { ApiError, telegramApi } from '@pinvi/api-client';
import type { TelegramTarget } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { SettingsList, SettingsSection } from '@/components/app/SettingsSurface';
import { FormField } from '@/components/forms/FormField';
import { buttonClassName } from '@/components/ui/Button';

function targetStatus(target: TelegramTarget): string {
  if (!target.is_enabled) return '비활성';
  if (!target.last_verified_at) return '미검증';
  return target.last_send_status === 'ok' ? '정상' : (target.last_send_status ?? '정상');
}

export default function TelegramTargetsSettingsPage() {
  const [targets, setTargets] = useState<TelegramTarget[]>([]);
  const [chatId, setChatId] = useState('');
  const [label, setLabel] = useState('');
  const [isDefault, setIsDefault] = useState(true);
  const [chatIdError, setChatIdError] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyTargetId, setBusyTargetId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chatIdRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setTargets(await telegramApi(apiClient).listTargets());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '조회 실패');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const run = async () => {
      await load();
    };
    void run();
  }, [load]);

  const onCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = chatId.trim();
    if (!trimmed) {
      setChatIdError('chat ID를 입력하세요.');
      chatIdRef.current?.focus();
      return;
    }
    setChatIdError(undefined);
    setSaving(true);
    setError(null);
    try {
      const created = await telegramApi(apiClient).createTarget({
        telegram_chat_id: trimmed,
        telegram_label: label.trim() || null,
        is_default: isDefault,
      });
      setTargets((prev) => [
        created,
        ...prev.map((t) => (created.is_default ? { ...t, is_default: false } : t)),
      ]);
      setChatId('');
      setLabel('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '등록 실패');
    } finally {
      setSaving(false);
    }
  };

  const onVerify = useCallback(
    async (targetId: string) => {
      setBusyTargetId(targetId);
      setError(null);
      try {
        const updated = await telegramApi(apiClient).verifyTarget(targetId);
        setTargets((prev) => prev.map((t) => (t.id === targetId ? updated : t)));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : '검증 실패');
        setLoading(true);
        await load();
      } finally {
        setBusyTargetId(null);
      }
    },
    [load],
  );

  const onDelete = useCallback(async (targetId: string) => {
    setBusyTargetId(targetId);
    setError(null);
    try {
      await telegramApi(apiClient).deleteTarget(targetId);
      setTargets((prev) => prev.filter((t) => t.id !== targetId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '삭제 실패');
    } finally {
      setBusyTargetId(null);
    }
  }, []);

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold text-ink">Telegram 알림</h1>
        <p className="text-sm text-muted">
          여행 생성·동반자 초대 알림을 받을 Telegram chat을 연결합니다. Pinvi 봇을 chat에 추가한 뒤
          chat ID를 등록하세요.
        </p>
        <p className="text-xs text-muted">
          ⚠️ 그룹/채널을 연결하면 그 방의 다른 사람도 알림을 볼 수 있습니다.
        </p>
      </header>

      {error && (
        <p
          role="alert"
          className="rounded-sm bg-error-bg p-3 text-sm text-error-text"
          data-testid="telegram-error"
        >
          {error}
        </p>
      )}

      <SettingsSection title="새 대상 연결">
        <form
          onSubmit={onCreate}
          className="grid items-start gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]"
          noValidate
        >
          <FormField
            ref={chatIdRef}
            id="telegram-chat-id"
            label="Chat ID"
            hint="예: -1001234567890 (그룹) 또는 123456789 (개인)"
            value={chatId}
            onChange={(e) => setChatId(e.target.value)}
            maxLength={64}
            error={chatIdError}
            data-testid="telegram-chat-id"
          />
          <FormField
            id="telegram-label"
            label="별칭 (선택)"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            maxLength={80}
            placeholder="가족 단톡"
            data-testid="telegram-label"
          />
          <label
            htmlFor="telegram-default"
            className="mt-7 inline-flex min-h-11 items-center gap-2 text-sm text-ink"
          >
            <input
              id="telegram-default"
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              data-testid="telegram-default"
            />
            기본 대상
          </label>
          <button
            type="submit"
            disabled={saving}
            className={buttonClassName({ className: 'mt-7' })}
            data-testid="telegram-create"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Send className="h-4 w-4" aria-hidden="true" />
            )}
            연결
          </button>
        </form>
      </SettingsSection>

      <SettingsSection title="연결된 대상">
        <SettingsList
          items={targets}
          loading={loading}
          aria-label="연결된 Telegram 대상"
          rowKey={(t) => t.id}
          empty="연결된 대상이 없습니다. 위에서 chat ID를 등록하면 알림을 받을 수 있습니다."
          renderRow={(t) => (
            <>
              <p className="flex items-center gap-1 text-base font-semibold text-ink">
                {t.is_default && <Star className="size-4 text-primary" aria-label="기본" />}
                {t.telegram_label ?? '—'}
              </p>
              <p className="mt-1 font-mono text-sm text-muted">
                {t.telegram_chat_id}
                {t.title_snapshot ? ` · ${t.title_snapshot}` : ''}
              </p>
              <p className="mt-1 text-sm text-muted">
                {t.telegram_chat_type ?? '—'} · {targetStatus(t)}
              </p>
            </>
          )}
          renderActions={(t) => (
            <>
              <button
                type="button"
                title="재검증"
                aria-label={`${t.telegram_label ?? t.telegram_chat_id} 재검증`}
                disabled={busyTargetId !== null}
                onClick={() => void onVerify(t.id)}
                className="focus-ring inline-flex size-11 items-center justify-center rounded-sm text-ink hover:bg-surface-soft disabled:opacity-40"
                data-testid={`telegram-verify-${t.telegram_chat_id}`}
              >
                <BadgeCheck className="h-4 w-4" aria-hidden="true" />
              </button>
              <button
                type="button"
                title="삭제"
                aria-label={`${t.telegram_label ?? t.telegram_chat_id} 삭제`}
                disabled={busyTargetId !== null}
                onClick={() => void onDelete(t.id)}
                className="focus-ring inline-flex size-11 items-center justify-center rounded-sm text-error-text hover:bg-error-bg disabled:opacity-40"
                data-testid={`telegram-delete-${t.telegram_chat_id}`}
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </button>
            </>
          )}
        />
      </SettingsSection>
    </div>
  );
}
