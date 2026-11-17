import { useMemo, useState } from 'react';
import { Alert, ScrollView, Text, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import { friendlyErrorText, placeWeatherCards, tripDaysToMapPoints } from '@pinvi/domain';
import { api } from '../../../../lib/api';
import { useTripMapLinking } from '../../../../lib/useTripMapLinking';
import { useTripTransport } from '../../../../lib/useTripTransport';
import { useVWorldToken } from '../../../../lib/vworldToken';
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
import { TripDayHeader } from '../../../../components/TripDayHeader';
import { TripMapPanel } from '../../../../components/TripMap';
import { TripPoiRow } from '../../../../components/TripPoiRow';

const SHARE_VISIBILITY_LABELS: Record<string, string> = {
  view_only: '읽기 전용',
  comment: '댓글 가능',
};

const STATUS_LABELS: Record<string, string> = {
  draft: '초안',
  planned: '계획됨',
  in_progress: '진행 중',
  completed: '완료',
  archived: '보관',
};

/** 지도 높이 — 화면의 절반(소유자: 지도 비중을 크게), 목록이 쓸 자리는 남긴다. */
function tripMapHeight(windowHeight: number): number {
  return Math.round(Math.min(560, Math.max(240, windowHeight * 0.5)));
}

function dateRange(start: string | null, end: string | null): string {
  if (!start && !end) return '날짜 미정';
  if (start && end) return start === end ? start : `${start} ~ ${end}`;
  return start ?? end ?? '';
}

/**
 * 여행 상세 — 웹 `(app)/trips/[tripId]` 대응(읽기). 위에 여행 지도, 아래에 일자별 POI + 공유 링크.
 *
 * 지도는 스크롤 밖에 고정해 지도 끌기와 목록 스크롤이 겹치지 않는다. 목록에서 장소를 누르면 지도가 그
 * 장소로 가고, 지도에서 장소를 누르면 목록의 그 줄이 강조되며 보이는 곳까지 스크롤된다.
 */
export default function TripDetailScreen() {
  const { tripId } = useLocalSearchParams<{ tripId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  // url/token은 생성 시 1회만 내려온다(share_links 목록엔 없음) → 화면에 보존.
  const [issuedShareUrl, setIssuedShareUrl] = useState<string | null>(null);
  const windowSize = useWindowDimensions();
  const tripQuery = useQuery({
    queryKey: queryKeys.trips.detail(tripId),
    queryFn: () => api.trips.get(tripId),
    enabled: Boolean(tripId),
  });

  const days = tripQuery.data?.days;
  const points = useMemo(() => (days ? tripDaysToMapPoints(days) : []), [days]);
  // 마커 이름 옆 날씨의 일자 카드(여행 응답에 이미 있다 — 새 요청 없음).
  const dayWeatherCards = useMemo(() => (days ? placeWeatherCards(days) : {}), [days]);
  const transport = useTripTransport({ active: true, points });

  const linking = useTripMapLinking(points);
  const vworldToken = useVWorldToken();

  const createShareMutation = useMutation({
    mutationFn: () => api.trips.createShareToken(tripId, { visibility: 'view_only' }),
    onSuccess: (link) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) });
      setIssuedShareUrl(link.url);
    },
    onError: (err) => Alert.alert('생성 실패', friendlyErrorText(err)),
  });

  const revokeShareMutation = useMutation({
    mutationFn: (shareId: string) => api.trips.revokeShareToken(tripId, shareId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.trips.detail(tripId) }),
    onError: (err) => Alert.alert('해제 실패', friendlyErrorText(err)),
  });

  // 파괴적 동작 — 해제 전 확인.
  function confirmRevoke(shareId: string) {
    Alert.alert(
      '공유 링크 해제',
      '이 공유 링크를 해제하면 더 이상 접근할 수 없습니다. 계속할까요?',
      [
        { text: '취소', style: 'cancel' },
        { text: '해제', style: 'destructive', onPress: () => revokeShareMutation.mutate(shareId) },
      ],
    );
  }

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
        <ErrorView
          message={friendlyErrorText(tripQuery.error)}
          onRetry={() => tripQuery.refetch()}
        />
      </Screen>
    );
  }

  const { trip, share_links, broken_feature_count } = tripQuery.data;
  const tripDays = tripQuery.data.days;

  return (
    <SafeAreaView className="flex-1 bg-canvas" edges={['bottom']}>
      <TripMapPanel
        points={points}
        selectedPoiId={linking.selectedPoiId}
        focus={linking.focus}
        onSelectPoi={linking.selectFromMap}
        transport={transport}
        vworldToken={vworldToken}
        collapsed={linking.mapCollapsed}
        onToggleCollapsed={linking.toggleMap}
        width={windowSize.width}
        height={tripMapHeight(windowSize.height)}
        tripId={tripId}
        dayWeatherCards={dayWeatherCards}
      />
      <ScrollView
        ref={linking.scrollRef}
        className="flex-1"
        contentContainerClassName="flex-grow"
        keyboardShouldPersistTaps="handled"
      >
        <View ref={linking.contentRef} className="gap-5 px-6 py-4">
          <View className="gap-2">
            <Heading>{trip.title}</Heading>
            <Muted>{dateRange(trip.start_date, trip.end_date)}</Muted>
            {trip.description ? <Body>{trip.description}</Body> : null}
            <View className="flex-row flex-wrap gap-2 pt-1">
              <Badge label={STATUS_LABELS[trip.status] ?? trip.status} />
              {broken_feature_count > 0 ? (
                <Badge label={`정보 사용 불가 ${broken_feature_count}`} />
              ) : null}
            </View>
            <Button
              label="편집"
              variant="secondary"
              onPress={() => router.push(`/trips/${tripId}/edit`)}
            />
          </View>

          {tripDays.length === 0 ? (
            <Muted>아직 일정이 없습니다.</Muted>
          ) : (
            tripDays.map((day) => (
              <Card key={day.day_index} className="gap-3">
                <TripDayHeader day={day} />
                {day.pois.length === 0 ? (
                  <Muted>이 날의 장소가 없습니다.</Muted>
                ) : (
                  <View className="gap-2.5">
                    {day.pois.map((poi) => (
                      <TripPoiRow
                        key={poi.poi_id}
                        poi={poi}
                        point={linking.pointById.get(poi.poi_id)}
                        selected={poi.poi_id === linking.selectedPoiId}
                        onPress={linking.selectFromList}
                        registerRow={linking.registerRow}
                        weatherTripId={tripId}
                      />
                    ))}
                  </View>
                )}
              </Card>
            ))
          )}

          <Card className="gap-3">
            <Subheading>공유 링크</Subheading>
            {share_links.length === 0 ? (
              <Muted>아직 공유 링크가 없습니다.</Muted>
            ) : (
              share_links.map((link) => {
                const revoked = Boolean(link.revoked_at);
                return (
                  <View key={link.share_id} className="flex-row items-center gap-2">
                    <View className="flex-1">
                      <Text className="text-sm text-ink">
                        {SHARE_VISIBILITY_LABELS[link.visibility] ?? link.visibility}
                      </Text>
                      <Muted>
                        {revoked
                          ? '해제됨'
                          : link.expires_at
                            ? `만료 ${link.expires_at.slice(0, 10)}`
                            : '무기한'}
                      </Muted>
                    </View>
                    {!revoked ? (
                      <Button
                        label="해제"
                        variant="secondary"
                        loading={
                          revokeShareMutation.isPending &&
                          revokeShareMutation.variables === link.share_id
                        }
                        onPress={() => confirmRevoke(link.share_id)}
                      />
                    ) : null}
                  </View>
                );
              })
            )}
            {issuedShareUrl ? (
              <View className="gap-2 rounded-md bg-surface-strong p-3">
                <Subheading>새 공유 링크</Subheading>
                <Text selectable className="text-sm text-ink">
                  {issuedShareUrl}
                </Text>
                <Muted>이 링크는 지금만 표시됩니다. 길게 눌러 복사해 안전한 곳에 보관하세요.</Muted>
                <Button label="숨기기" variant="ghost" onPress={() => setIssuedShareUrl(null)} />
              </View>
            ) : null}
            <Button
              label="공유 링크 만들기"
              onPress={() => createShareMutation.mutate()}
              loading={createShareMutation.isPending}
            />
          </Card>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
