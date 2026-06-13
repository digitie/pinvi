import {
  TelegramTargetCreateSchema,
  TelegramTargetSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';

/** `/users/me/telegram-targets` — `docs/integrations/telegram.md` §6 (T-106). */
export const telegramApi = (client: ApiClient) => ({
  listTargets: () =>
    client.request('/users/me/telegram-targets', {
      method: 'GET',
      schema: z.array(TelegramTargetSchema),
    }),

  createTarget: (body: z.input<typeof TelegramTargetCreateSchema>) =>
    client.request('/users/me/telegram-targets', {
      method: 'POST',
      body: JSON.stringify(TelegramTargetCreateSchema.parse(body)),
      schema: TelegramTargetSchema,
    }),

  verifyTarget: (targetId: string) =>
    client.request(`/users/me/telegram-targets/${targetId}/verify`, {
      method: 'POST',
      schema: TelegramTargetSchema,
    }),

  deleteTarget: (targetId: string) =>
    client.requestNoContent(`/users/me/telegram-targets/${targetId}`, {
      method: 'DELETE',
    }),

  // trip ↔ target 연결 (§6.5/6.6)
  listTripTargets: (tripId: string) =>
    client.request(`/trips/${tripId}/telegram-targets`, {
      method: 'GET',
      schema: z.array(TelegramTargetSchema),
    }),

  linkTripTarget: (tripId: string, targetId: string) =>
    client.request(`/trips/${tripId}/telegram-targets`, {
      method: 'POST',
      body: JSON.stringify({ telegram_target_id: targetId }),
      schema: TelegramTargetSchema,
    }),

  unlinkTripTarget: (tripId: string, targetId: string) =>
    client.requestNoContent(`/trips/${tripId}/telegram-targets/${targetId}`, {
      method: 'DELETE',
    }),
});
