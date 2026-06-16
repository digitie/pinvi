import { View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { friendlyErrorText, paletteHex } from '@pinvi/domain';
import { api } from '../../../lib/api';
import {
  Badge,
  Body,
  Card,
  ErrorView,
  Heading,
  Loading,
  Muted,
  Screen,
  Subheading,
} from '../../../components/ui';

function dateRange(start: string | null, end: string | null): string {
  if (!start && !end) return '날짜 미정';
  if (start && end) return start === end ? start : `${start} ~ ${end}`;
  return start ?? end ?? '';
}

/**
 * 익명 공유 뷰 — 웹 `shared/[tripId]/[token]` 대응. 인증 그룹 밖(로그인 불필요).
 * 공유 토큰으로 읽기 전용 일정(`buildShareUrl` 딥링크: `pinvi://shared/:tripId/:token`).
 */
export default function SharedTripScreen() {
  const { tripId, token } = useLocalSearchParams<{ tripId: string; token: string }>();

  const sharedQuery = useQuery({
    queryKey: ['shared', tripId, token],
    queryFn: () => api.trips.getShared(tripId, token),
    enabled: Boolean(tripId && token),
    retry: false,
  });

  if (sharedQuery.isLoading) {
    return (
      <Screen scroll={false}>
        <Loading />
      </Screen>
    );
  }
  if (sharedQuery.isError || !sharedQuery.data) {
    return (
      <Screen>
        <ErrorView
          message={
            sharedQuery.error
              ? friendlyErrorText(sharedQuery.error)
              : '공유 링크가 만료되었거나 올바르지 않습니다.'
          }
        />
      </Screen>
    );
  }

  const { trip, days, broken_feature_count } = sharedQuery.data;

  return (
    <Screen>
      <View className="gap-5 py-2">
        <View className="gap-2">
          <Muted>공유된 여행</Muted>
          <Heading>{trip.title}</Heading>
          <Muted>{dateRange(trip.start_date, trip.end_date)}</Muted>
          {trip.description ? <Body>{trip.description}</Body> : null}
          {broken_feature_count > 0 ? <Badge label={`연결 끊김 ${broken_feature_count}`} /> : null}
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
                      <Body className="flex-1 font-medium text-ink">
                        {poi.title ?? '제목 없는 장소'}
                      </Body>
                    </View>
                  ))}
                </View>
              )}
            </Card>
          ))
        )}
      </View>
    </Screen>
  );
}
