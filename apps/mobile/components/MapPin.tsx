import { Text, View } from 'react-native';
import type { WeatherConditionKind } from '@pinvi/domain';
import { mapPinSize } from './mapPinLayout';
import { MarkerIcon } from './MarkerIcon';
import { WeatherIcon } from './WeatherIcon';

const LABEL_MAX_WIDTH = 120;

export interface MapPinWeather {
  condition: WeatherConditionKind;
  night: boolean;
}

/**
 * 작은 원 마커 + (있으면) 원 안 아이콘·상자 없는 이름 라벨·이름 옆 현재 날씨 — 웹 여행 지도(#755) 대응.
 * 라벨은 원 아래에 붙는다. 원 중심을 좌표에 맞추는 자리는 `mapPinPlacement`가 정한다. 날씨를 모르면
 * 날씨 아이콘을 그리지 않는다.
 */
export function MapPin({
  color,
  label,
  selected,
  compact = false,
  icon,
  weather,
}: {
  color: string;
  label?: string;
  selected?: boolean;
  compact?: boolean;
  icon?: string;
  weather?: MapPinWeather | null;
}) {
  const size = mapPinSize({ compact, selected, icon });
  const circle = (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color,
        borderWidth: selected ? 3 : 2,
        borderColor: '#ffffff',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {icon && !compact ? (
        <MarkerIcon icon={icon} size={Math.round(size * 0.6)} color="#ffffff" />
      ) : null}
    </View>
  );
  if (!label) return circle;
  return (
    <View style={{ alignItems: 'center' }}>
      {circle}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
        <Text
          numberOfLines={1}
          style={{
            lineHeight: 16,
            maxWidth: LABEL_MAX_WIDTH,
            fontSize: 11,
            fontWeight: selected ? '700' : '600',
            color: '#222222',
            // 상자 없이 바탕지도 위에서 읽히도록 흰 테두리(halo).
            textShadowColor: '#ffffff',
            textShadowRadius: 3,
            textShadowOffset: { width: 0, height: 0 },
          }}
        >
          {label}
        </Text>
        {weather ? (
          // 아이콘은 halo를 못 두르므로 흰 바탕 원 위에 그린다.
          <View
            testID="map-pin-weather"
            style={{ borderRadius: 8, backgroundColor: '#ffffff', padding: 1 }}
          >
            <WeatherIcon condition={weather.condition} night={weather.night} size={12} />
          </View>
        ) : null}
      </View>
    </View>
  );
}
