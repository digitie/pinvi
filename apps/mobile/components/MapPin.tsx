import { Text, View } from 'react-native';

/** 이름 라벨 한 줄의 높이 — 원 위 빈칸과 같아야 원 중심이 좌표에 온다. */
const MAP_PIN_LABEL_HEIGHT = 16;
const LABEL_MAX_WIDTH = 120;

/** 마커 크기 — 여행 장소(이름 있음)는 16, 보조 마커(교통 등)는 더 작게 12. 고르면 커진다. */
function pinSize(compact: boolean, selected: boolean | undefined): number {
  if (compact) return selected ? 18 : 12;
  return selected ? 22 : 16;
}

/**
 * 작은 원 마커 + (있으면) 상자 없는 이름 라벨 — 웹 여행 지도(#755)의 원 + 이름 대응.
 *
 * 네이티브·웹 지도 모두 마커 내용의 **가운데**를 좌표에 맞춘다(`vworld-map-rn` 1.0.1 Marker는 anchor를 열지 않는다).
 * 그래서 라벨이 있으면 원 위에 라벨과 같은 높이의 빈칸을 두어 세로로 대칭을 만들고, 가로는 가운데 정렬한다 —
 * 원 중심이 좌표다.
 *
 * TODO(vworld-map-rn 1.0.2): 재vendor 뒤 Marker `anchor`/`offset`(maplibre-vworld-react #34)으로 원 중심을 맞추고
 * 위 빈칸을 지운다(웹 어댑터도 `anchor`를 쓴다).
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
  const size = pinSize(compact, selected);
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
      <View style={{ height: MAP_PIN_LABEL_HEIGHT }} />
      {circle}
      <Text
        numberOfLines={1}
        style={{
          height: MAP_PIN_LABEL_HEIGHT,
          lineHeight: MAP_PIN_LABEL_HEIGHT,
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
