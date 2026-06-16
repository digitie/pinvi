import { Alert, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ConsentType, UserConsent } from '@pinvi/schemas';
import { friendlyErrorText } from '@pinvi/domain';
import { api } from '../../../lib/api';
import {
  Badge,
  Body,
  Button,
  Card,
  ErrorView,
  Heading,
  Loading,
  Muted,
  Screen,
  Subheading,
} from '../../../components/ui';

const CONSENTS_KEY = ['consents'] as const;

const CONSENTS: { type: ConsentType; label: string; required: boolean; note?: string }[] = [
  { type: 'tos', label: '이용약관', required: true },
  { type: 'privacy', label: '개인정보 처리방침', required: true },
  { type: 'lbs_tos', label: '위치기반서비스 이용약관', required: true },
  {
    type: 'location_collection',
    label: '개인위치정보 수집·이용',
    required: true,
    note: '철회하면 내 위치·주변 검색 등 위치 기능이 비활성화됩니다(위치정보법 제16조).',
  },
  { type: 'demographic_use', label: '인구통계 정보 이용', required: false },
  { type: 'marketing', label: '마케팅·이벤트 수신', required: false },
];

// 필수 약관 철회는 회원 탈퇴 수준이라 본 화면에서는 제외(웹과 동일).
const WITHDRAWABLE: ConsentType[] = ['location_collection', 'demographic_use', 'marketing'];

function statusOf(consents: UserConsent[], type: ConsentType): 'agreed' | 'withdrawn' | 'none' {
  const row = consents.find((c) => c.consent_type === type);
  if (!row) return 'none';
  return row.withdrawn_at ? 'withdrawn' : 'agreed';
}

const STATUS_TEXT: Record<'agreed' | 'withdrawn' | 'none', string> = {
  agreed: '동의함',
  withdrawn: '철회함',
  none: '미동의',
};

/** 동의 관리 — 웹 `(app)/settings/consents` 대응. 현황 확인 + 선택 항목 철회. */
export default function ConsentsSettingsScreen() {
  const queryClient = useQueryClient();
  const consentsQuery = useQuery({ queryKey: CONSENTS_KEY, queryFn: () => api.user.getConsents() });

  const withdrawMutation = useMutation({
    mutationFn: (type: ConsentType) => api.user.withdrawConsent(type),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CONSENTS_KEY }),
    onError: (err) => Alert.alert('철회 실패', friendlyErrorText(err)),
  });

  return (
    <Screen>
      <View className="gap-5 py-2">
        <View className="gap-1">
          <Heading>동의 관리</Heading>
          <Body>동의 현황을 확인하고 선택 항목을 철회할 수 있습니다.</Body>
        </View>

        {consentsQuery.isPending ? (
          <Loading />
        ) : consentsQuery.isError ? (
          <ErrorView message={friendlyErrorText(consentsQuery.error)} onRetry={() => consentsQuery.refetch()} />
        ) : (
          <View className="gap-3">
            {CONSENTS.map((meta) => {
              const status = statusOf(consentsQuery.data, meta.type);
              const canWithdraw = WITHDRAWABLE.includes(meta.type) && status === 'agreed';
              return (
                <Card key={meta.type} className="gap-2">
                  <View className="flex-row items-center gap-2">
                    <Subheading className="flex-1">{meta.label}</Subheading>
                    <Badge label={meta.required ? '필수' : '선택'} />
                  </View>
                  <Muted>
                    {STATUS_TEXT[status]}
                    {meta.note ? ` · ${meta.note}` : ''}
                  </Muted>
                  {canWithdraw ? (
                    <Button
                      label="철회"
                      variant="secondary"
                      loading={withdrawMutation.isPending && withdrawMutation.variables === meta.type}
                      onPress={() => withdrawMutation.mutate(meta.type)}
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
