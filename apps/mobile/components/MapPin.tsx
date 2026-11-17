import { Text, View } from 'react-native';
import { mapPinSize } from './mapPinLayout';

const LABEL_MAX_WIDTH = 120;

/**
 * 작은 원 마커 + (있으면) 상자 없는 이름 라벨 — 웹 여행 지도(#755)의 원 + 이름 대응.
 * 라벨이 있으면 원 아래에 붙는다. 원 중심을 좌표에 맞추는 자리는 `mapPinPlacement`가 정한다.
 */
export function MapPin({
  color,
  label,
  selected,
  compact = false,
}: {
  color: string;
  label?: string;
  selected?: boolean;
  compact?: boolean;
}) {
  const size = mapPinSize(compact, selected);
  const circle = (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: color,
        borderWidth: selected ? 3 : 2,
        borderColor: '#ffffff',
      }}
    />
  );
  if (!label) return circle;
  return (
    <View style={{ alignItems: 'center' }}>
      {circle}
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
    </View>
  );
}
