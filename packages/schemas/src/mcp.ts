import { z } from 'zod';
import { Iso8601Schema } from './common';

export const McpScopeSchema = z.literal('mcp:read');
export type McpScope = z.infer<typeof McpScopeSchema>;

export const McpTokenStatusSchema = z.enum(['active', 'expired', 'revoked']);
export type McpTokenStatus = z.infer<typeof McpTokenStatusSchema>;

export const McpTokenIssueRequestSchema = z.object({
  name: z.string().min(1).max(120),
  expires_at: Iso8601Schema.nullable().optional(),
  scopes: z.array(McpScopeSchema).optional().default(['mcp:read']),
});
export type McpTokenIssueRequest = z.infer<typeof McpTokenIssueRequestSchema>;

export const AdminMcpTokenIssueRequestSchema = McpTokenIssueRequestSchema.extend({
  user_id: z.string().uuid(),
  access_reason: z.string().min(1).max(500),
});
export type AdminMcpTokenIssueRequest = z.infer<typeof AdminMcpTokenIssueRequestSchema>;

export const McpTokenRevokeRequestSchema = z.object({
  access_reason: z.string().min(1).max(500),
});
export type McpTokenRevokeRequest = z.infer<typeof McpTokenRevokeRequestSchema>;

export const McpTokenSchema = z.object({
  token_id: z.string().uuid(),
  user_id: z.string().uuid().nullable().optional(),
  name: z.string(),
  scopes: z.array(McpScopeSchema),
  masked_token: z.string(),
  expires_at: Iso8601Schema.nullable(),
  last_used_at: Iso8601Schema.nullable(),
  revoked_at: Iso8601Schema.nullable(),
  created_at: Iso8601Schema,
});
export type McpToken = z.infer<typeof McpTokenSchema>;

export const McpTokenIssueResponseSchema = McpTokenSchema.extend({
  token: z.string().min(1),
});
export type McpTokenIssueResponse = z.infer<typeof McpTokenIssueResponseSchema>;
