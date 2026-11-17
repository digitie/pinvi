import { useCallback, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  Text,
  useWindowDimensions,
  View,
  type HostInstance,
  type ScrollViewInstance,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@pinvi/api-client';
import type { TripViewPoi } from '@pinvi/schemas';
import {
  featureResolutionNotice,
  friendlyErrorText,
  paletteHex,
  placeWeatherCards,
  tripDaysToMapPoints,
  type TripMapPoint,
} from '@pinvi/domain';
import { api } from '../../../../lib/api';
import { useTripTransport } from '../../../../lib/useTripTransport';
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
import { TripMapPanel, type TripMapFocus } from '../../../../components/TripMap';
import { PoiWeatherBadge } from '../../../../components/PoiWeatherBadge';

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
  const [mapCollapsed, setMapCollapsed] = useState(false);
  const [selectedPoiId, setSelectedPoiId] = useState<string | null>(null);
  const [focus, setFocus] = useState<TripMapFocus | null>(null);
  const scrollRef = useRef<ScrollViewInstance>(null);
  const contentRef = useRef<HostInstance>(null);
  const rowRefs = useRef(new Map<string, HostInstance>());

  const tripQuery = useQuery({
    queryKey: queryKeys.trips.detail(tripId),
    queryFn: () => api.trips.get(tripId),
    enabled: Boolean(tripId),
  });

  const days = tripQuery.data?.days;
  const points = useMemo(() => (days ? tripDaysToMapPoints(days) : []), [days]);
  const pointById = useMemo(() => new Map(points.map((p) => [p.poiId, p])), [points]);
  // 마커 이름 옆 날씨의 일자 카드(여행 응답에 이미 있다 — 새 요청 없음).
  const dayWeatherCards = useMemo(() => (days ? placeWeatherCards(days) : {}), [days]);
  const transport = useTripTransport({ active: true, points });

  /** 목록 → 지도: 그 장소를 고르고 지도 가운데로(접혀 있으면 펼치며 그 장소로 연다). */
  const selectFromList = useCallback(
    (poiId: string) => {
      setSelectedPoiId(poiId);
      if (!pointById.has(poiId)) return;
      setMapCollapsed(false);
      setFocus((prev) => ({ poiId, seq: (prev?.seq ?? 0) + 1 }));
    },
    [pointById],
  );

  /** 지도 → 목록: 그 줄을 강조하고 보이는 곳까지 스크롤한다. */
  const selectFromMap = useCallback((poiId: string) => {
    setSelectedPoiId(poiId);
    const row = rowRefs.current.get(poiId);
    const content = contentRef.current;
    if (!row || !content) return;
    row.measureLayout(
      content,
      (_x, y) => scrollRef.current?.scrollTo({ y: Math.max(0, y - 12), animated: true }),
      () => undefined,
    );
  }, []);

  const registerRow = useCallback((poiId: string, node: HostInstance | null) => {
    if (node) rowRefs.current.set(poiId, node);
    else rowRefs.current.delete(poiId);
  }, []);

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
        selectedPoiId={selectedPoiId}
        focus={focus}
        onSelectPoi={selectFromMap}
        transport={transport}
        collapsed={mapCollapsed}
        onToggleCollapsed={() => setMapCollapsed((prev) => !prev)}
        width={windowSize.width}
        height={tripMapHeight(windowSize.height)}
        tripId={tripId}
        dayWeatherCards={dayWeatherCards}
      />
      <ScrollView
        ref={scrollRef}
        className="flex-1"
        contentContainerClassName="flex-grow"
        keyboardShouldPersistTaps="handled"
      >
        <View ref={contentRef} className="gap-5 px-6 py-4">
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
                        tripId={tripId}
                        poi={poi}
                        point={pointById.get(poi.poi_id)}
                        selected={poi.poi_id === selectedPoiId}
                        onPress={selectFromList}
                        registerRow={registerRow}
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

/**
 * 일정의 장소 한 줄. 점 색은 지도 마커와 같은 값(서버 `display_marker_color` 우선, ADR-055)이다.
 * 누르면 지도에서 그 장소로 간다(좌표가 없으면 줄만 고른다).
 */
function TripPoiRow({
  tripId,
  poi,
  point,
  selected,
  onPress,
  registerRow,
}: {
  tripId: string;
  poi: TripViewPoi;
  point: TripMapPoint | undefined;
  selected: boolean;
  onPress: (poiId: string) => void;
  registerRow: (poiId: string, node: HostInstance | null) => void;
}) {
  const resolutionNotice = featureResolutionNotice(poi.feature_resolution_state);
  const title = poi.title ?? '제목 없는 장소';
  return (
    <Pressable
      ref={(node) => registerRow(poi.poi_id, node)}
      accessibilityRole="button"
      aria-selected={selected}
      accessibilityHint={point ? '지도에서 이 장소로 이동합니다' : undefined}
      onPress={() => onPress(poi.poi_id)}
      testID={`trip-poi-row-${poi.poi_id}`}
      className={`-mx-2 flex-row items-start gap-3 rounded-md px-2 py-1.5 ${selected ? 'bg-surface-strong' : ''}`}
    >
      <View
        className="mt-1 h-3 w-3 rounded-full"
        style={{
          backgroundColor: point?.color ?? paletteHex(poi.display_marker_color ?? poi.marker_color),
        }}
      />
      <View className="flex-1">
        <Body className="font-medium text-ink">
          {title}
          {resolutionNotice ? ` · (${resolutionNotice})` : ''}
        </Body>
        {point ? (
          // 좌표를 아는 장소만 현재 날씨를 묻는다(공유 캐시·동시 2건, 모르면 아무것도 그리지 않는다).
          <PoiWeatherBadge tripId={tripId} poiId={poi.poi_id} />
        ) : null}
        {poi.user_note ? <Muted>{poi.user_note}</Muted> : null}
        {point ? null : <Muted>좌표가 없어 지도에 표시하지 않습니다.</Muted>}
      </View>
    </Pressable>
  );
}
