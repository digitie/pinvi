import { View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import { friendlyErrorText, paletteHex } from '@pinvi/domain';
import { api } from '../../../../lib/api';
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
} from '../../../../components/ui';

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

/** 여행 상세 — 웹 `(app)/trips/[tripId]` 대응(읽기). 일자별 POI + 공유 링크. */
export default function TripDetailScreen() {
  const { tripId } = useLocalSearchParams<{ tripId: string }>();
  const router = useRouter();

  const tripQuery = useQuery({
    queryKey: queryKeys.trips.detail(tripId),
    queryFn: () => api.trips.get(tripId),
    enabled: Boolean(tripId),
  });

  if (tripQuery.isLoading) {
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

  const { trip, days, share_links, broken_feature_count } = tripQuery.data;

  return (
    <Screen>
      <View className="gap-5 py-2">
        <View className="gap-2">
          <Heading>{trip.title}</Heading>
          <Muted>{dateRange(trip.start_date, trip.end_date)}</Muted>
          {trip.description ? <Body>{trip.description}</Body> : null}
          <View className="flex-row flex-wrap gap-2 pt-1">
            <Badge label={STATUS_LABELS[trip.status] ?? trip.status} />
            {broken_feature_count > 0 ? <Badge label={`연결 끊김 ${broken_feature_count}`} /> : null}
          </View>
          <Button
            label="편집"
            variant="secondary"
            onPress={() => router.push(`/trips/${tripId}/edit`)}
          />
        </View>

        {days.length === 0 ? (
          <Muted>아직 일정이 없습니다.</Muted>
        ) : (
          days.map((day) => (
            <Card key={day.day_index} className="gap-3">
              <Subheading>
                Day {day.day_index}
                {day.title ? ` · ${day.title}` : ''}
                {day.date ? ` (${day.date})` : ''}
              </Subheading>
              {day.pois.length === 0 ? (
                <Muted>이 날의 장소가 없습니다.</Muted>
              ) : (
                <View className="gap-2.5">
                  {day.pois.map((poi) => (
                    <View key={poi.poi_id} className="flex-row items-start gap-3">
                      <View
                        className="mt-1 h-3 w-3 rounded-full"
                        style={{ backgroundColor: paletteHex(poi.marker_color) }}
                      />
                      <View className="flex-1">
                        <Body className="font-medium text-ink">
                          {poi.title ?? '제목 없는 장소'}
                          {poi.is_broken ? ' · (연결 끊김)' : ''}
                        </Body>
                        {poi.user_note ? <Muted>{poi.user_note}</Muted> : null}
                      </View>
                    </View>
                  ))}
                </View>
              )}
            </Card>
          ))
        )}

        {share_links.length > 0 ? (
          <Card className="gap-2">
            <Subheading>공유 링크</Subheading>
            {share_links.map((link) => (
              <Muted key={link.share_id}>
                {link.visibility}
                {link.revoked_at ? ' · 해제됨' : link.expires_at ? ` · 만료 ${link.expires_at}` : ''}
              </Muted>
            ))}
          </Card>
        ) : null}
      </View>
    </Screen>
  );
}
