import {
  McpTokenIssueRequestSchema,
  McpTokenIssueResponseSchema,
  McpTokenSchema,
} from '@tripmate/schemas';
import { z } from 'zod';
import type { ApiClient } from '../client';

export const userApi = (client: ApiClient) => ({
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
