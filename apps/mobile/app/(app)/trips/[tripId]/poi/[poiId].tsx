import { useState } from 'react';
import { View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import type { PoiUpdate, TripView, TripViewPoi } from '@pinvi/schemas';
import { friendlyErrorText, validateAmountInput } from '@pinvi/domain';
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

/** trip 뷰에서 POI 1건만 투영 — 없으면 null(뷰는 있는데 POI가 없는 경우와 로딩을 구분). */
function selectPoi(view: TripView, poiId: string): TripViewPoi | null {
  for (const day of view.days) {
    const found = day.pois.find((p) => p.poi_id === poiId);
    if (found) return found;
  }
  return null;
}

/**
 * POI 필드 편집 — 메모/비용. `poiApi.update`(If-Match version). 여행 편집 화면에서 진입.
 * 마커/시간 등 나머지 필드는 후속.
 */
export default function PoiEditScreen() {
  const { tripId, poiId } = useLocalSearchParams<{ tripId: string; poiId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  // 단건 POI GET이 없어 trip 뷰 캐시를 쓰되, `select`로 이 POI만 구독한다(issue #215/#206 —
  // 다른 POI/일자 변경으로는 리렌더하지 않고, 목록 화면과 캐시를 공유해 추가 요청도 없다).
  const poiQuery = useQuery({
    queryKey: queryKeys.trips.detail(tripId),
    queryFn: () => api.trips.get(tripId),
    enabled: Boolean(tripId),
    select: (view) => selectPoi(view, poiId),
  });
  const poi = poiQuery.data ?? null;

  // 입력값 = 사용자 편집본(있으면) ?? 서버 값(렌더 중 파생, effect seed 없음).
  // poi.budget_amount는 decimal string이라 그대로 초기값으로 쓴다.
  const [noteEdit, setNoteEdit] = useState<string | null>(null);
  const [budgetEdit, setBudgetEdit] = useState<string | null>(null);
  const note = noteEdit ?? poi?.user_note ?? '';
  const budget = budgetEdit ?? poi?.budget_amount ?? '';
  const [error, setError] = useState<string | null>(null);
  const [budgetError, setBudgetError] = useState<string | null>(null);

  const saveMutation = useMutation({
    mutationFn: (body: PoiUpdate) => {
      if (!poi) throw new Error('not ready');
      return api.pois.update(tripId, poi.poi_id, poi.version, body);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) });
      router.back();
    },
    onError: (err) => setError(friendlyErrorText(err)),
  });

  if (poiQuery.isLoading) {
    return (
      <Screen scroll={false}>
        <Loading />
      </Screen>
    );
  }
  if (poiQuery.isError) {
    return (
      <Screen>
        <ErrorView message={friendlyErrorText(poiQuery.error)} onRetry={() => poiQuery.refetch()} />
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
    // 예산 검증(issue #215/#206) — 음수/비숫자/지수는 서버 ZodError 대신 사용자 문구로 차단.
    const amount = validateAmountInput(budget);
    if (!amount.ok) {
      setBudgetError(amount.message);
      return;
    }
    setBudgetError(null);
    setError(null);
    saveMutation.mutate({ user_note: note.trim() || null, budget_amount: amount.value });
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
            onChangeText={setNoteEdit}
            multiline
            numberOfLines={4}
            className="min-h-24"
            placeholder="이 장소에 대한 메모"
          />
          <Field
            label={`예산 (${poi.currency})`}
            value={budget}
            onChangeText={(v) => {
              setBudgetEdit(v);
              setBudgetError(null);
            }}
            error={budgetError ?? undefined}
            keyboardType="numeric"
            placeholder="예: 30000"
          />
          <Button label="저장" onPress={onSave} loading={saveMutation.isPending} />
        </Card>
      </View>
    </Screen>
  );
}
