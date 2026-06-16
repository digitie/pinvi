import { Alert, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import { buildCopyRequest, friendlyErrorText } from '@pinvi/domain';
import { api } from '../../../lib/api';
import {
  Badge,
  Body,
  Button,
  Card,
  EmptyState,
  ErrorView,
  Heading,
  Loading,
  Muted,
  Screen,
  Subheading,
} from '../../../components/ui';

function dateRange(start: string | null, end: string | null): string {
  if (!start && !end) return '';
  if (start && end) return start === end ? start : `${start} ~ ${end}`;
  return start ?? end ?? '';
}

/** 추천 여행(notice-plans) — 웹 `(app)/notice-plans` 대응. 목록 + 내 여행으로 복사. */
export default function NoticePlansScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();

  const plansQuery = useQuery({
    queryKey: queryKeys.noticePlans.list({}),
    queryFn: () => api.noticePlans.list({ limit: 50 }),
  });

  const copyMutation = useMutation({
    mutationFn: ({ planId, title }: { planId: string; title: string }) =>
      api.noticePlans.copy(
        planId,
        buildCopyRequest({ mode: 'new', title, startDate: '', endDate: '', targetTripId: null }),
      ),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.trips.all() });
      Alert.alert('복사 완료', '추천 여행을 내 여행으로 복사했습니다.', [
        { text: '여행 보기', onPress: () => router.push(`/trips/${result.trip_id}`) },
        { text: '닫기', style: 'cancel' },
      ]);
    },
    onError: (err) => {
      Alert.alert('복사 실패', friendlyErrorText(err));
    },
  });

  return (
    <Screen>
      <View className="gap-4 py-2">
        <Heading>추천 여행</Heading>

        {plansQuery.isPending ? (
          <Loading />
        ) : plansQuery.isError ? (
          <ErrorView message={friendlyErrorText(plansQuery.error)} onRetry={() => plansQuery.refetch()} />
        ) : plansQuery.data.length === 0 ? (
          <EmptyState title="추천 여행이 아직 없습니다" description="새로운 큐레이션 일정이 곧 추가됩니다." />
        ) : (
          <View className="gap-3">
            {plansQuery.data.map((plan) => {
              const pending =
                copyMutation.isPending && copyMutation.variables?.planId === plan.notice_plan_id;
              return (
                <Card key={plan.notice_plan_id} className="gap-2">
                  <View className="flex-row items-start justify-between gap-2">
                    <Subheading className="flex-1">{plan.title}</Subheading>
                    <Badge label={plan.category} />
                  </View>
                  {plan.summary ? <Body>{plan.summary}</Body> : null}
                  <Muted>
                    {[dateRange(plan.starts_on, plan.ends_on), `장소 ${plan.pois.length}곳`]
                      .filter(Boolean)
                      .join(' · ')}
                  </Muted>
                  <Button
                    label="내 여행으로 복사"
                    variant="secondary"
                    loading={pending}
                    onPress={() =>
                      copyMutation.mutate({ planId: plan.notice_plan_id, title: plan.title })
                    }
                  />
                </Card>
              );
            })}
          </View>
        )}
      </View>
    </Screen>
  );
}
