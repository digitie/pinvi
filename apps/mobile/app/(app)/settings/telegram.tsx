import { useState } from 'react';
import { Alert, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { TelegramTarget } from '@pinvi/schemas';
import { friendlyErrorText } from '@pinvi/domain';
import { api } from '../../../lib/api';
import {
  Badge,
  Body,
  Button,
  Card,
  Checkbox,
  EmptyState,
  ErrorBanner,
  ErrorView,
  Field,
  Heading,
  Loading,
  Muted,
  Screen,
  Subheading,
} from '../../../components/ui';

const TELEGRAM_KEY = ['telegram', 'targets'] as const;

function statusOf(t: TelegramTarget): string {
  if (!t.is_enabled) return '비활성';
  if (!t.last_verified_at) return '미검증';
  return t.last_send_status === 'ok' ? '정상' : (t.last_send_status ?? '정상');
}

/** Telegram 알림 대상 관리 — 웹 `(app)/settings/telegram` 대응. */
export default function TelegramSettingsScreen() {
  const queryClient = useQueryClient();
  const [chatId, setChatId] = useState('');
  const [label, setLabel] = useState('');
  const [isDefault, setIsDefault] = useState(true);
  const [formError, setFormError] = useState<string | null>(null);

  const targetsQuery = useQuery({ queryKey: TELEGRAM_KEY, queryFn: () => api.telegram.listTargets() });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: TELEGRAM_KEY });

  const createMutation = useMutation({
    mutationFn: () =>
      api.telegram.createTarget({
        telegram_chat_id: chatId.trim(),
        telegram_label: label.trim() || null,
        is_default: isDefault,
      }),
    onSuccess: () => {
      setChatId('');
      setLabel('');
      setFormError(null);
      void invalidate();
    },
    onError: (err) => setFormError(friendlyErrorText(err)),
  });

  const verifyMutation = useMutation({
    mutationFn: (targetId: string) => api.telegram.verifyTarget(targetId),
    onSuccess: () => invalidate(),
    onError: (err) => Alert.alert('검증 실패', friendlyErrorText(err)),
  });

  const deleteMutation = useMutation({
    mutationFn: (targetId: string) => api.telegram.deleteTarget(targetId),
    onSuccess: () => invalidate(),
    onError: (err) => Alert.alert('삭제 실패', friendlyErrorText(err)),
  });

  const onCreate = () => {
    if (!chatId.trim()) {
      setFormError('chat ID를 입력하세요.');
      return;
    }
    createMutation.mutate();
  };

  const busyId = verifyMutation.isPending
    ? verifyMutation.variables
    : deleteMutation.isPending
      ? deleteMutation.variables
      : null;

  return (
    <Screen>
      <View className="gap-5 py-2">
        <View className="gap-1">
          <Heading>Telegram 알림</Heading>
          <Body>
            여행 생성·동반자 초대 알림을 받을 chat을 연결합니다. Pinvi 봇을 chat에 추가한 뒤 chat
            ID를 등록하세요.
          </Body>
          <Muted>⚠️ 그룹/채널을 연결하면 그 방의 다른 사람도 알림을 볼 수 있습니다.</Muted>
        </View>

        <Card className="gap-3">
          <Subheading>새 대상 연결</Subheading>
          <ErrorBanner message={formError} />
          <Field
            label="Chat ID"
            value={chatId}
            onChangeText={setChatId}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
            maxLength={64}
            placeholder="예: -1001234567890 또는 123456789"
          />
          <Field
            label="별칭 (선택)"
            value={label}
            onChangeText={setLabel}
            maxLength={80}
            placeholder="예: 가족 여행방"
          />
          <Checkbox checked={isDefault} onToggle={setIsDefault} label="기본 대상으로 설정" />
          <Button label="연결" onPress={onCreate} loading={createMutation.isPending} />
        </Card>

        {targetsQuery.isPending ? (
          <Loading />
        ) : targetsQuery.isError ? (
          <ErrorView message={friendlyErrorText(targetsQuery.error)} onRetry={() => targetsQuery.refetch()} />
        ) : targetsQuery.data.length === 0 ? (
          <EmptyState title="연결된 대상이 없습니다" description="위에서 chat ID를 등록해 보세요." />
        ) : (
          <View className="gap-3">
            {targetsQuery.data.map((t) => (
              <Card key={t.id} className="gap-2">
                <View className="flex-row items-start justify-between gap-2">
                  <Subheading className="flex-1">{t.telegram_label ?? t.telegram_chat_id}</Subheading>
                  <View className="flex-row gap-1.5">
                    {t.is_default ? <Badge label="기본" /> : null}
                    <Badge label={statusOf(t)} />
                  </View>
                </View>
                <Muted>
                  {t.telegram_chat_id}
                  {t.title_snapshot ? ` · ${t.title_snapshot}` : ''}
                  {t.telegram_chat_type ? ` · ${t.telegram_chat_type}` : ''}
                </Muted>
                <View className="flex-row gap-2 pt-1">
                  <Button
                    label="재검증"
                    variant="secondary"
                    className="flex-1"
                    loading={verifyMutation.isPending && busyId === t.id}
                    disabled={busyId !== null && busyId !== t.id}
                    onPress={() => verifyMutation.mutate(t.id)}
                  />
                  <Button
                    label="삭제"
                    variant="danger"
                    className="flex-1"
                    loading={deleteMutation.isPending && busyId === t.id}
                    disabled={busyId !== null && busyId !== t.id}
                    onPress={() => deleteMutation.mutate(t.id)}
                  />
                </View>
              </Card>
            ))}
          </View>
        )}
      </View>
    </Screen>
  );
}
