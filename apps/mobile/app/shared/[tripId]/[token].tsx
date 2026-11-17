import { useMemo } from 'react';
import { ScrollView, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { friendlyErrorText, placeWeatherCards, tripDaysToMapPoints } from '@pinvi/domain';
import { api } from '../../../lib/api';
import { useTripMapLinking } from '../../../lib/useTripMapLinking';
import { useSharedVWorldToken } from '../../../lib/vworldToken';
import {
  Badge,
  Body,
  Card,
  ErrorView,
  Heading,
  Loading,
  Muted,
  Screen,
} from '../../../components/ui';
import { TripDayHeader } from '../../../components/TripDayHeader';
import { TripMapPanel } from '../../../components/TripMap';
import { TripPoiRow } from '../../../components/TripPoiRow';

/** 지도 높이 — 여행 상세와 같이 화면의 절반, 목록이 쓸 자리는 남긴다. */
function sharedMapHeight(windowHeight: number): number {
  return Math.round(Math.min(560, Math.max(240, windowHeight * 0.5)));
}

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
  const windowSize = useWindowDimensions();

  const sharedQuery = useQuery({
    queryKey: ['shared', tripId, token],
    queryFn: () => api.trips.getShared(tripId, token),
    enabled: Boolean(tripId && token),
    retry: false,
  });

  const days = sharedQuery.data?.days;
  const points = useMemo(() => (days ? tripDaysToMapPoints(days) : []), [days]);
  // 마커 이름 옆 날씨는 공유 응답의 일자 카드에서만(장소별 날씨 API는 로그인 필요 — 웹 공유 화면과 같다).
  const dayWeatherCards = useMemo(() => (days ? placeWeatherCards(days) : {}), [days]);
  const linking = useTripMapLinking(points);
  // 지도 키는 이 공유 토큰 범위로만 받는다(모바일은 키를 번들하지 않는다 — ADR-043).
  const vworldToken = useSharedVWorldToken(tripId, token);

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

  const { trip, broken_feature_count } = sharedQuery.data;
  const sharedDays = sharedQuery.data.days;

  return (
    <SafeAreaView className="flex-1 bg-canvas" edges={['top', 'bottom']}>
      {/* 웹 공유 화면과 같이 교통 칩은 없다(`/transport/*`는 로그인 필요, NEAR-027). */}
      <TripMapPanel
        points={points}
        selectedPoiId={linking.selectedPoiId}
        focus={linking.focus}
        onSelectPoi={linking.selectFromMap}
        vworldToken={vworldToken}
        collapsed={linking.mapCollapsed}
        onToggleCollapsed={linking.toggleMap}
        width={windowSize.width}
        height={sharedMapHeight(windowSize.height)}
        dayWeatherCards={dayWeatherCards}
      />
      <ScrollView ref={linking.scrollRef} className="flex-1" contentContainerClassName="flex-grow">
        <View ref={linking.contentRef} className="gap-5 px-6 py-4">
          <View className="gap-2">
            <Muted>공유된 여행</Muted>
            <Heading>{trip.title}</Heading>
            <Muted>{dateRange(trip.start_date, trip.end_date)}</Muted>
            {trip.description ? <Body>{trip.description}</Body> : null}
            {broken_feature_count > 0 ? (
              <Badge label={`정보 사용 불가 ${broken_feature_count}`} />
            ) : null}
          </View>

          {sharedDays.length === 0 ? (
            <Muted>아직 일정이 없습니다.</Muted>
          ) : (
            sharedDays.map((day) => (
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
                        showNote={false}
                      />
                    ))}
                  </View>
                )}
              </Card>
            ))
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}
