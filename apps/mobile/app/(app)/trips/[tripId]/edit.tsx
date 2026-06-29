import { useEffect, useState } from 'react';
import { Alert, Pressable, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import type { TripStatus, TripVisibility, TripViewPoi } from '@pinvi/schemas';
import {
  STATUS_LABEL,
  VISIBILITY_LABEL,
  arrayMove,
  buildTripUpdate,
  friendlyErrorText,
  paletteHex,
  reorderMoves,
  type TripEditForm,
} from '@pinvi/domain';
import { api } from '../../../../lib/api';
import {
  Body,
  Button,
  Card,
  ChipGroup,
  ErrorBanner,
  ErrorView,
  Field,
  Heading,
  Loading,
  Muted,
  Screen,
  Subheading,
} from '../../../../components/ui';

const VISIBILITY_OPTIONS = (Object.keys(VISIBILITY_LABEL) as TripVisibility[]).map((v) => ({
  value: v,
  label: VISIBILITY_LABEL[v],
}));
const STATUS_OPTIONS = (Object.keys(STATUS_LABEL) as TripStatus[]).map((s) => ({
  value: s,
  label: STATUS_LABEL[s],
}));

/**
 * 여행 편집 — 메타 수정(`tripApi.update`, If-Match version) + 일자별 POI 재정렬
 * (`reorderMoves` + `poiApi.reorder`) + POI 삭제. POI 필드(메모/비용) 편집은 후속.
 */
export default function TripEditScreen() {
  const { tripId } = useLocalSearchParams<{ tripId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const tripQuery = useQuery({
    queryKey: queryKeys.trips.detail(tripId),
    queryFn: () => api.trips.get(tripId),
    enabled: Boolean(tripId),
  });

  const [form, setForm] = useState<TripEditForm | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  // 일자별 POI 순서(낙관적). 서버 데이터 로드 시 시드.
  const [order, setOrder] = useState<Record<number, string[]>>({});

  useEffect(() => {
    if (!tripQuery.data) return;
    const { trip, days } = tripQuery.data;
    setForm((current) =>
      current ?? {
        title: trip.title,
        regionHint: trip.region_hint ?? '',
        startDate: trip.start_date ?? '',
        endDate: trip.end_date ?? '',
        visibility: trip.visibility,
        status: trip.status,
      },
    );
    setOrder((current) => {
      if (Object.keys(current).length > 0) return current;
      const seeded: Record<number, string[]> = {};
      for (const day of days) {
        seeded[day.day_index] = day.pois.map((p) => p.poi_id);
      }
      return seeded;
    });
  }, [tripQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!form || !tripQuery.data) throw new Error('not ready');
      return api.trips.update(tripId, tripQuery.data.trip.version, buildTripUpdate(form));
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.trips.all() });
      router.back();
    },
    onError: (err) => setFormError(friendlyErrorText(err)),
  });

  const reorderMutation = useMutation({
    mutationFn: (moves: { poi_id: string; new_sort_order: string }[]) =>
      api.pois.reorder(tripId, { moves }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) }),
    onError: (err) => Alert.alert('재정렬 실패', friendlyErrorText(err)),
  });

  const deleteMutation = useMutation({
    mutationFn: (poiId: string) => api.pois.delete(tripId, poiId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) }),
    onError: (err) => Alert.alert('삭제 실패', friendlyErrorText(err)),
  });

  const addDayMutation = useMutation({
    mutationFn: (dayIndex: number) => api.trips.createDay(tripId, { day_index: dayIndex }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) }),
    onError: (err) => Alert.alert('일자 추가 실패', friendlyErrorText(err)),
  });

  const deleteDayMutation = useMutation({
    mutationFn: ({ dayIndex, version }: { dayIndex: number; version: number }) =>
      api.trips.deleteDay(tripId, dayIndex, version),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) }),
    onError: (err) => Alert.alert('일자 삭제 실패', friendlyErrorText(err)),
  });

  const deleteTripMutation = useMutation({
    mutationFn: () => api.trips.delete(tripId, { mode: 'soft_delete' }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.trips.all() });
      router.replace('/trips');
    },
    onError: (err) => Alert.alert('여행 삭제 실패', friendlyErrorText(err)),
  });

  if (tripQuery.isLoading || !form) {
    return (
      <Screen scroll={false}>
        <Loading />
      </Screen>
    );
  }
  if (tripQuery.isError || !tripQuery.data) {
    return (
      <Screen>
        <ErrorView message={friendlyErrorText(tripQuery.error)} onRetry={() => tripQuery.refetch()} />
      </Screen>
    );
  }

  const { days } = tripQuery.data;
  const poiById = new Map<string, TripViewPoi>();
  for (const day of days) {
    for (const poi of day.pois) poiById.set(poi.poi_id, poi);
  }
  const nextDayIndex = days.reduce((max, d) => Math.max(max, d.day_index), 0) + 1;

  const onDeleteDay = (dayIndex: number, version: number) => {
    Alert.alert('일자 삭제', `Day ${dayIndex}와(과) 그 안의 장소를 삭제할까요?`, [
      { text: '취소', style: 'cancel' },
      {
        text: '삭제',
        style: 'destructive',
        onPress: () => deleteDayMutation.mutate({ dayIndex, version }),
      },
    ]);
  };

  const onDeleteTrip = () => {
    Alert.alert('여행 삭제', '이 여행을 삭제할까요? 되돌릴 수 없습니다.', [
      { text: '취소', style: 'cancel' },
      { text: '삭제', style: 'destructive', onPress: () => deleteTripMutation.mutate() },
    ]);
  };

  const move = (dayIndex: number, from: number, to: number) => {
    const current = order[dayIndex] ?? [];
    if (to < 0 || to >= current.length) return;
    const next = arrayMove(current, from, to);
    setOrder((prev) => ({ ...prev, [dayIndex]: next }));
    const day = days.find((d) => d.day_index === dayIndex);
    const currentSortById = new Map<string, string>();
    for (const p of day?.pois ?? []) currentSortById.set(p.poi_id, p.sort_order);
    const moves = reorderMoves(next, currentSortById);
    if (moves.length > 0) reorderMutation.mutate(moves);
  };

  const onDelete = (poiId: string, title: string) => {
    Alert.alert('장소 삭제', `"${title}"을(를) 삭제할까요?`, [
      { text: '취소', style: 'cancel' },
      {
        text: '삭제',
        style: 'destructive',
        onPress: () => {
          setOrder((prev) => {
            const next: Record<number, string[]> = {};
            for (const [k, ids] of Object.entries(prev)) {
              next[Number(k)] = ids.filter((id) => id !== poiId);
            }
            return next;
          });
          deleteMutation.mutate(poiId);
        },
      },
    ]);
  };

  const onSave = () => {
    if (!form.title.trim()) {
      setFormError('제목을 입력해 주세요.');
      return;
    }
    setFormError(null);
    saveMutation.mutate();
  };

  return (
    <Screen>
      <View className="gap-5 py-2">
        <Heading>여행 편집</Heading>

        <Card className="gap-3">
          <Subheading>기본 정보</Subheading>
          <ErrorBanner message={formError} />
          <Field
            label="제목"
            value={form.title}
            onChangeText={(title) => setForm({ ...form, title })}
            maxLength={200}
          />
          <Field
            label="지역 (선택)"
            value={form.regionHint}
            onChangeText={(regionHint) => setForm({ ...form, regionHint })}
            maxLength={120}
            placeholder="예: 제주"
          />
          <Field
            label="시작일 (YYYY-MM-DD)"
            value={form.startDate}
            onChangeText={(startDate) => setForm({ ...form, startDate })}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
            placeholder="2026-07-01"
          />
          <Field
            label="종료일 (YYYY-MM-DD)"
            value={form.endDate}
            onChangeText={(endDate) => setForm({ ...form, endDate })}
            autoCapitalize="none"
            keyboardType="numbers-and-punctuation"
            placeholder="2026-07-03"
          />
          <ChipGroup
            label="공개 범위"
            value={form.visibility}
            options={VISIBILITY_OPTIONS}
            onChange={(visibility) => setForm({ ...form, visibility })}
          />
          <ChipGroup
            label="상태"
            value={form.status}
            options={STATUS_OPTIONS}
            onChange={(status) => setForm({ ...form, status })}
          />
          <Button label="저장" onPress={onSave} loading={saveMutation.isPending} />
        </Card>

        <View className="gap-1">
          <Subheading>일정 · 장소</Subheading>
          <Muted>↑/↓로 순서 변경, 장소를 눌러 메모/예산 편집, 삭제로 제거. 변경은 즉시 저장됩니다.</Muted>
        </View>

        {days.length === 0 ? (
          <Muted>아직 일정이 없습니다.</Muted>
        ) : (
          days.map((day) => {
            const ids = order[day.day_index] ?? day.pois.map((p) => p.poi_id);
            return (
              <Card key={day.day_index} className="gap-3">
                <View className="flex-row items-center gap-2">
                  <Subheading className="flex-1">
                    Day {day.day_index}
                    {day.title ? ` · ${day.title}` : ''}
                    {day.date ? ` (${day.date})` : ''}
                  </Subheading>
                  <Button
                    label="일자 삭제"
                    variant="secondary"
                    loading={
                      deleteDayMutation.isPending &&
                      deleteDayMutation.variables?.dayIndex === day.day_index
                    }
                    onPress={() => onDeleteDay(day.day_index, day.version)}
                  />
                </View>
                {ids.length === 0 ? (
                  <Muted>이 날의 장소가 없습니다.</Muted>
                ) : (
                  ids.map((poiId, index) => {
                    const poi = poiById.get(poiId);
                    if (!poi) return null;
                    return (
                      <View key={poiId} className="gap-1.5 border-t border-hairline-soft pt-2">
                        <Pressable
                          accessibilityRole="button"
                          onPress={() => router.push(`/trips/${tripId}/poi/${poiId}`)}
                          className="flex-row items-center gap-2 active:opacity-70"
                        >
                          <View
                            className="h-3 w-3 rounded-full"
                            style={{ backgroundColor: paletteHex(poi.marker_color) }}
                          />
                          <Body className="flex-1 text-ink">{poi.title ?? '제목 없는 장소'}</Body>
                          <Muted>편집 ›</Muted>
                        </Pressable>
                        <View className="flex-row gap-2">
                          <Button
                            label="↑"
                            variant="secondary"
                            className="flex-1"
                            disabled={index === 0 || reorderMutation.isPending}
                            onPress={() => move(day.day_index, index, index - 1)}
                          />
                          <Button
                            label="↓"
                            variant="secondary"
                            className="flex-1"
                            disabled={index === ids.length - 1 || reorderMutation.isPending}
                            onPress={() => move(day.day_index, index, index + 1)}
                          />
                          <Button
                            label="삭제"
                            variant="danger"
                            className="flex-1"
                            onPress={() => onDelete(poiId, poi.title ?? '이 장소')}
                          />
                        </View>
                      </View>
                    );
                  })
                )}
              </Card>
            );
          })
        )}

        <Button
          label="+ 일자 추가"
          variant="secondary"
          loading={addDayMutation.isPending}
          onPress={() => addDayMutation.mutate(nextDayIndex)}
        />

        <View className="mt-4 gap-2 border-t border-hairline-soft pt-4">
          <Subheading>위험 구역</Subheading>
          <Button
            label="여행 삭제"
            variant="danger"
            loading={deleteTripMutation.isPending}
            onPress={onDeleteTrip}
          />
        </View>
      </View>
    </Screen>
  );
}
