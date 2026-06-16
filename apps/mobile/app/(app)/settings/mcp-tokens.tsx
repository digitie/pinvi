import { useState } from 'react';
import { Alert, Pressable, Text, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { McpToken } from '@pinvi/schemas';
import { friendlyErrorText } from '@pinvi/domain';
import { api } from '../../../lib/api';
import {
  Badge,
  Body,
  Button,
  Card,
  ErrorView,
  Field,
  Heading,
  Loading,
  Muted,
  Screen,
  Subheading,
} from '../../../components/ui';

const MCP_KEY = ['mcp-tokens'] as const;

const EXPIRY_OPTIONS = [
  { value: '30', label: '30일' },
  { value: '7', label: '7일' },
  { value: '90', label: '90일' },
  { value: 'never', label: '무기한' },
] as const;
type ExpiryValue = (typeof EXPIRY_OPTIONS)[number]['value'];

function addDays(days: number): string {
  const expires = new Date();
  expires.setDate(expires.getDate() + days);
  return expires.toISOString();
}

function tokenStatus(token: McpToken): string {
  if (token.revoked_at) return 'revoked';
  if (token.expires_at && new Date(token.expires_at).getTime() <= Date.now()) return 'expired';
  return 'active';
}

/** MCP 토큰 — 웹 `(app)/settings/mcp-tokens` 대응. 발급(원문 1회 표시) + 회수. */
export default function McpTokensSettingsScreen() {
  const queryClient = useQueryClient();
  const [name, setName] = useState('Claude Desktop');
  const [expiry, setExpiry] = useState<ExpiryValue>('30');
  const [issued, setIssued] = useState<string | null>(null);

  const tokensQuery = useQuery({ queryKey: MCP_KEY, queryFn: () => api.user.listMcpTokens() });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: MCP_KEY });

  const issueMutation = useMutation({
    mutationFn: () =>
      api.user.issueMcpToken(
        expiry === 'never'
          ? { name, expires_at: null }
          : { name, expires_at: addDays(Number(expiry)) },
      ),
    onSuccess: (created) => {
      setIssued(created.token);
      void invalidate();
    },
    onError: (err) => Alert.alert('발급 실패', friendlyErrorText(err)),
  });

  const revokeMutation = useMutation({
    mutationFn: (tokenId: string) => api.user.revokeMcpToken(tokenId),
    onSuccess: () => invalidate(),
    onError: (err) => Alert.alert('회수 실패', friendlyErrorText(err)),
  });

  return (
    <Screen>
      <View className="gap-5 py-2">
        <Heading>MCP 토큰</Heading>

        <Card className="gap-3">
          <Subheading>새 토큰</Subheading>
          <Field label="토큰 이름" value={name} onChangeText={setName} maxLength={120} />
          <View className="gap-1.5">
            <Text className="text-sm font-medium text-ink">만료</Text>
            <View className="flex-row flex-wrap gap-2">
              {EXPIRY_OPTIONS.map((opt) => {
                const active = expiry === opt.value;
                return (
                  <Pressable
                    key={opt.value}
                    accessibilityRole="button"
                    accessibilityState={{ selected: active }}
                    onPress={() => setExpiry(opt.value)}
                    className={`rounded-sm border px-3 py-2 ${active ? 'border-primary bg-primary' : 'border-hairline bg-canvas'}`}
                  >
                    <Text className={`text-sm font-medium ${active ? 'text-white' : 'text-body'}`}>
                      {opt.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>
          <Button label="발급" onPress={() => issueMutation.mutate()} loading={issueMutation.isPending} />

          {issued ? (
            <View className="gap-1.5 rounded-md bg-success-bg p-3">
              <Body className="text-success-text">발급된 토큰 (지금만 표시됩니다 — 길게 눌러 복사):</Body>
              <Text selectable className="font-mono text-xs text-ink">
                {issued}
              </Text>
            </View>
          ) : null}
        </Card>

        {tokensQuery.isPending ? (
          <Loading />
        ) : tokensQuery.isError ? (
          <ErrorView message={friendlyErrorText(tokensQuery.error)} onRetry={() => tokensQuery.refetch()} />
        ) : tokensQuery.data.length === 0 ? (
          <Muted>발급된 토큰이 없습니다.</Muted>
        ) : (
          <View className="gap-3">
            {tokensQuery.data.map((token) => {
              const revoked = Boolean(token.revoked_at);
              return (
                <Card key={token.token_id} className="gap-2">
                  <View className="flex-row items-center gap-2">
                    <Subheading className="flex-1">{token.name}</Subheading>
                    <Badge label={tokenStatus(token)} />
                  </View>
                  <Muted className="font-mono">{token.masked_token}</Muted>
                  <Muted>만료: {token.expires_at ? token.expires_at.slice(0, 10) : '무기한'}</Muted>
                  {!revoked ? (
                    <Button
                      label="회수"
                      variant="danger"
                      loading={revokeMutation.isPending && revokeMutation.variables === token.token_id}
                      onPress={() => revokeMutation.mutate(token.token_id)}
                    />
                  ) : null}
                </Card>
              );
            })}
          </View>
        )}
      </View>
    </Screen>
  );
}
