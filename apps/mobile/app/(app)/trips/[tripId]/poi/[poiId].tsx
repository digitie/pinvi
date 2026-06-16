import { useEffect, useState } from 'react';
import { View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import type { PoiUpdate, TripViewPoi } from '@pinvi/schemas';
import { friendlyErrorText } from '@pinvi/domain';
import { api } from '../../../../../lib/api';
import {
  Body,
  Button,
  Card,
  ErrorBanner,
  ErrorView,
  Field,
  Heading,
  Loading,
  Muted,
  Screen,
} from '../../../../../components/ui';

/**
 * POI 필드 편집 — 메모/비용. `poiApi.update`(If-Match version). 여행 편집 화면에서 진입.
 * 마커/시간 등 나머지 필드는 후속.
 */
export default function PoiEditScreen() {
  const { tripId, poiId } = useLocalSearchParams<{ tripId: string; poiId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const tripQuery = useQuery({
    queryKey: queryKeys.trips.detail(tripId),
    queryFn: () => api.trips.get(tripId),
    enabled: Boolean(tripId),
  });

  const poi: TripViewPoi | undefined = tripQuery.data?.days
    .flatMap((d) => d.pois)
    .find((p) => p.poi_id === poiId);

  const [note, setNote] = useState('');
  const [budget, setBudget] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!poi) return;
    setNote((current) => (current === '' ? (poi.user_note ?? '') : current));
    setBudget((current) => (current === '' ? (poi.budget_amount ?? '') : current));
    // poi.budget_amount는 decimal string. 초기값만 시드.
  }, [poi]);

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!poi) throw new Error('not ready');
      const trimmedBudget = budget.trim();
      const body: PoiUpdate = {
        user_note: note.trim() || null,
        budget_amount: trimmedBudget === '' ? null : Number(trimmedBudget),
      };
      return api.pois.update(tripId, poi.poi_id, poi.version, body);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) });
      router.back();
    },
    onError: (err) => setError(friendlyErrorText(err)),
  });

  if (tripQuery.isLoading) {
    return (
      <Screen scroll={false}>
        <Loading />
      </Screen>
    );
  }
  if (tripQuery.isError) {
    return (
      <Screen>
        <ErrorView message={friendlyErrorText(tripQuery.error)} onRetry={() => tripQuery.refetch()} />
      </Screen>
    );
  }
  if (!poi) {
    return (
      <Screen>
        <Muted>장소를 찾을 수 없습니다.</Muted>
      </Screen>
    );
  }

  const onSave = () => {
    const trimmedBudget = budget.trim();
    if (trimmedBudget !== '' && !Number.isFinite(Number(trimmedBudget))) {
      setError('예산은 숫자로 입력해 주세요.');
      return;
    }
    setError(null);
    saveMutation.mutate();
  };

  return (
    <Screen>
      <View className="gap-5 py-2">
        <View className="gap-1">
          <Heading>장소 편집</Heading>
          <Body>{poi.title ?? '제목 없는 장소'}</Body>
        </View>

        <Card className="gap-3">
          <ErrorBanner message={error} />
          <Field
            label="메모"
            value={note}
            onChangeText={setNote}
            multiline
            numberOfLines={4}
            className="min-h-24"
            placeholder="이 장소에 대한 메모"
          />
          <Field
            label={`예산 (${poi.currency})`}
            value={budget}
            onChangeText={setBudget}
            keyboardType="numeric"
            placeholder="예: 30000"
          />
          <Button label="저장" onPress={onSave} loading={saveMutation.isPending} />
        </Card>
      </View>
    </Screen>
  );
}
