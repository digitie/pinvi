import { Pressable, View, type HostInstance } from 'react-native';
import type { TripViewPoi } from '@pinvi/schemas';
import { featureResolutionNotice, paletteHex, type TripMapPoint } from '@pinvi/domain';
import { PoiWeatherBadge } from './PoiWeatherBadge';
import { Body, Muted } from './ui';

/**
 * 일정의 장소 한 줄(여행 상세·공유 화면 공용). 점 색은 지도 마커와 같은 값(서버 `display_marker_color` 우선,
 * ADR-055)이다. 누르면 지도에서 그 장소로 간다(좌표가 없으면 줄만 고른다).
 *
 * `weatherTripId`가 있으면(로그인한 여행 화면) 좌표를 아는 장소의 현재 날씨 배지를 단다 — 장소별 날씨 API는
 * 로그인이 필요해 공유 화면은 넘기지 않는다.
 */
export function TripPoiRow({
  poi,
  point,
  selected,
  onPress,
  registerRow,
  weatherTripId = null,
  showNote = true,
}: {
  poi: Pick<
    TripViewPoi,
    | 'poi_id'
    | 'title'
    | 'feature_resolution_state'
    | 'display_marker_color'
    | 'marker_color'
    | 'user_note'
  >;
  point: TripMapPoint | undefined;
  selected: boolean;
  onPress: (poiId: string) => void;
  registerRow: (poiId: string, node: HostInstance | null) => void;
  weatherTripId?: string | null;
  showNote?: boolean;
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
        {point && weatherTripId ? (
          // 좌표를 아는 장소만 현재 날씨를 묻는다(공유 캐시·동시 2건, 모르면 아무것도 그리지 않는다).
          <PoiWeatherBadge tripId={weatherTripId} poiId={poi.poi_id} />
        ) : null}
        {showNote && poi.user_note ? <Muted>{poi.user_note}</Muted> : null}
        {point ? null : <Muted>좌표가 없어 지도에 표시하지 않습니다.</Muted>}
      </View>
    </Pressable>
  );
}
