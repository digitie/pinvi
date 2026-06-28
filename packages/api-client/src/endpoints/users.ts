import {
  ConsentTypeSchema,
  ContentReportAppealRequestSchema,
  ContentReportCreateRequestSchema,
  ContentReportListResponseSchema,
  ContentReportRecordSchema,
  DsrRequestCreateRequestSchema,
  DsrRequestListResponseSchema,
  DsrRequestRecordSchema,
  DsrRequestWithdrawRequestSchema,
  McpTokenIssueRequestSchema,
  McpTokenIssueResponseSchema,
  McpTokenSchema,
  UserConsentSchema,
} from '@pinvi/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';
import type { ConsentType } from '@pinvi/schemas';

const ConsentItemsSchema = z.array(
  z.object({ consent_type: ConsentTypeSchema, version: z.string().min(1).max(32) }),
);

export type DsrRequestCreateBody = z.input<typeof DsrRequestCreateRequestSchema>;
export type DsrRequestWithdrawBody = z.input<typeof DsrRequestWithdrawRequestSchema>;
export type ContentReportCreateBody = z.input<typeof ContentReportCreateRequestSchema>;
export type ContentReportAppealBody = z.input<typeof ContentReportAppealRequestSchema>;

export const userApi = (client: ApiClient) => ({
  deleteMe: () =>
    client.requestNoContent('/users/me', {
      method: 'DELETE',
    }),

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

  listDsrRequests: (pageSize = 50) => {
    const qs = new URLSearchParams();
    qs.set('page_size', String(pageSize));
    return client.request(`/users/me/dsr-requests?${qs.toString()}`, {
      method: 'GET',
      schema: DsrRequestListResponseSchema,
    });
  },

  createDsrRequest: (body: DsrRequestCreateBody) =>
    client.request('/users/me/dsr-requests', {
      method: 'POST',
      body: JSON.stringify(DsrRequestCreateRequestSchema.parse(body)),
      schema: DsrRequestRecordSchema,
    }),

  withdrawDsrRequest: (requestId: string, body: DsrRequestWithdrawBody) =>
    client.request(`/users/me/dsr-requests/${encodeURIComponent(requestId)}/withdraw`, {
      method: 'POST',
      body: JSON.stringify(DsrRequestWithdrawRequestSchema.parse(body)),
      schema: DsrRequestRecordSchema,
    }),

  listContentReports: (pageSize = 50) => {
    const qs = new URLSearchParams();
    qs.set('page_size', String(pageSize));
    return client.request(`/users/me/content-reports?${qs.toString()}`, {
      method: 'GET',
      schema: ContentReportListResponseSchema,
    });
  },

  createContentReport: (body: ContentReportCreateBody) =>
    client.request('/users/me/content-reports', {
      method: 'POST',
      body: JSON.stringify(ContentReportCreateRequestSchema.parse(body)),
      schema: ContentReportRecordSchema,
    }),

  appealContentReport: (reportId: string, body: ContentReportAppealBody) =>
    client.request(`/users/me/content-reports/${encodeURIComponent(reportId)}/appeal`, {
      method: 'POST',
      body: JSON.stringify(ContentReportAppealRequestSchema.parse(body)),
      schema: ContentReportRecordSchema,
    }),
});
