import { z } from 'zod';
import { Iso8601Schema } from './common';

/** Telegram 알림 대상 — `docs/integrations/telegram.md` §6 (T-106).
 * bot token은 받지 않는다(§1) — 시스템 봇을 chat에 추가한 뒤 chat_id만 등록.
 */
export const TelegramTargetCreateSchema = z.object({
  telegram_chat_id: z.string().min(1).max(64),
  telegram_label: z.string().max(80).nullable().optional(),
  telegram_message_thread_id: z.string().max(64).nullable().optional(),
  is_default: z.boolean().optional().default(false),
});
export type TelegramTargetCreate = z.infer<typeof TelegramTargetCreateSchema>;

export const TelegramTargetSchema = z.object({
  id: z.string().uuid(),
  telegram_chat_id: z.string(),
  telegram_chat_type: z.string().nullable(),
  telegram_message_thread_id: z.string().nullable(),
  telegram_label: z.string().nullable(),
  title_snapshot: z.string().nullable(),
  is_default: z.boolean(),
  is_enabled: z.boolean(),
  last_verified_at: Iso8601Schema.nullable(),
  last_send_status: z.string().nullable(),
  created_at: Iso8601Schema,
});
export type TelegramTarget = z.infer<typeof TelegramTargetSchema>;
