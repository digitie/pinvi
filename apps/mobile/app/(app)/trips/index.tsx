import { useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import { useDebounce } from '@pinvi/hooks';
import { friendlyErrorText } from '@pinvi/domain';
import { api } from '../../../lib/api';
import {
  Badge,
  Body,
  EmptyState,
  ErrorView,
  Loading,
  Muted,
  Screen,
  Subheading,
} from '../../../components/ui';

const STATUS_LABELS: Record<string, string> = {
  draft: '초안',
  planned: '계획됨',
  in_progress: '진행 중',
  completed: '완료',
  archived: '보관',
};

function dateRange(start: string | null, end: string | null): string {
  if (!start && !end) return '날짜 미정';
  if (start && end) return start === end ? start : `${start} ~ ${end}`;
  return start ?? end ?? '';
}

/** 내 여행 목록 — 웹 `(app)/trips` 대응. 검색 + 카드 목록 + 상세 이동. */
export default function TripsScreen() {
  const router = useRouter();
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 300);

  const tripsQuery = useQuery({
    queryKey: [...queryKeys.trips.list({ bucket: 'all' }), debounced],
    queryFn: () => api.trips.listPage({ bucket: 'all', q: debounced || undefined, limit: 50 }),
  });

  return (
    <Screen>
      <View className="gap-4 py-2">
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="여행 검색"
          placeholderTextColor="#929292"
          autoCapitalize="none"
          className="min-h-11 rounded-md border border-hairline bg-canvas px-3 py-2.5 text-base text-ink"
        />

        {tripsQuery.isPending ? (
          <Loading />
        ) : tripsQuery.isError ? (
          <ErrorView message={friendlyErrorText(tripsQuery.error)} onRetry={() => tripsQuery.refetch()} />
        ) : tripsQuery.data.items.length === 0 ? (
          <EmptyState
            title={debounced ? '검색 결과가 없습니다' : '아직 여행이 없습니다'}
            description={debounced ? '다른 검색어를 시도해 보세요.' : '추천 여행에서 일정을 복사해 시작해 보세요.'}
          />
        ) : (
          <View className="gap-3">
            {tripsQuery.data.items.map((trip) => (
              <Pressable
                key={trip.trip_id}
                accessibilityRole="button"
                onPress={() => router.push(`/trips/${trip.trip_id}`)}
                className="gap-1.5 rounded-md border border-hairline-soft bg-canvas p-4 active:opacity-80"
              >
                <Subheading>{trip.title}</Subheading>
                <Muted>{dateRange(trip.start_date, trip.end_date)}</Muted>
                {trip.region_hint ? <Body>{trip.region_hint}</Body> : null}
                <Badge label={STATUS_LABELS[trip.status] ?? trip.status} />
              </Pressable>
            ))}
          </View>
        )}
      </View>
    </Screen>
  );
}
