import {
  ConsentTypeSchema,
  McpTokenIssueRequestSchema,
  McpTokenIssueResponseSchema,
  McpTokenSchema,
  UserConsentSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type { ConsentType } from '@tripmate/schemas';

const ConsentItemsSchema = z.array(
  z.object({ consent_type: ConsentTypeSchema, version: z.string().min(1).max(32) })
);

export const userApi = (client: ApiClient) => ({
  /** 현재 사용자의 동의 목록(`docs/api/users.md` §3). */
  getConsents: () =>
    client.request('/users/consents', {
      method: 'GET',
      schema: z.array(UserConsentSchema),
    }),

  /** 동의 기록(idempotent). 위치 기능 등 추가 동의 시 사용. */
  putConsents: (items: { consent_type: ConsentType; version: string }[]) =>
    client.request('/users/consents', {
      method: 'PUT',
      body: JSON.stringify(ConsentItemsSchema.parse(items)),
      schema: z.array(UserConsentSchema),
    }),

  /** 동의 철회(`location_collection` 철회 시 위치 기능 비활성, LBS 제16조). */
  withdrawConsent: (consentType: ConsentType) =>
    client.requestNoContent(`/users/consents/${consentType}`, {
      method: 'DELETE',
    }),

  listMcpTokens: () =>
    client.request('/users/me/mcp-tokens', {
      method: 'GET',
      schema: z.array(McpTokenSchema),
    }),

  issueMcpToken: (body: z.input<typeof McpTokenIssueRequestSchema>) =>
    client.request('/users/me/mcp-tokens', {
      method: 'POST',
      body: JSON.stringify(McpTokenIssueRequestSchema.parse(body)),
      schema: McpTokenIssueResponseSchema,
    }),

  revokeMcpToken: (tokenId: string) =>
    client.requestNoContent(`/users/me/mcp-tokens/${tokenId}`, {
      method: 'DELETE',
    }),
});
