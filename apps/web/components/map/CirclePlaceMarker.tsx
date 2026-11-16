'use client';

import { PlaceWeatherGlyph, type PlaceWeatherSource } from '@/components/map/PlaceWeatherGlyph';
import { Marker } from '@/components/map/vworldPrimitives';
import type { ComponentProps, ReactNode } from 'react';

type MarkerProps = ComponentProps<typeof Marker>;

// 라벨 글자 halo — 구글 지도처럼 상자 없이 흰 테두리만으로 어떤 바탕 위에서도 읽힌다.
const LABEL_HALO =
  '-1px -1px 0 #fff, 1px -1px 0 #fff, -1px 1px 0 #fff, 1px 1px 0 #fff, 0 0 3px #fff, 0 0 3px #fff';

export interface CirclePlaceMarkerProps
  extends Omit<MarkerProps, 'children' | 'anchor' | 'offset' | 'color'> {
  /** 원 채움색(hex). */
  color: string;
  /** 원 지름(px). 원의 중심이 좌표다. */
  size: number;
  /** 원 안 아이콘(흰색). */
  icon: ReactNode;
  /** 원 오른쪽에 상자 없이 쓰는 이름. 없으면 원만 그린다. */
  label?: string;
  /** 라벨 옆 현재 날씨 아이콘의 출처(이미 받은 카드). 날씨를 모르면 아이콘은 그리지 않는다. */
  weather?: PlaceWeatherSource | null;
}

/**
 * 구글 지도식 장소 마커 — 흰 테두리 원 + 오른쪽에 상자 없는 이름 + 날씨 아이콘.
 *
 * 마커 요소의 왼쪽 가운데를 좌표에 걸고(`anchor: 'left'`) 반지름만큼 왼쪽으로 옮겨, 라벨 길이와
 * 무관하게 **원의 중심**이 좌표에 온다. 요소 높이는 원 지름으로 고정하고 라벨은 그 안에서 세로
 * 가운데 정렬한다. 라벨도 마커 요소의 일부라 이름을 눌러도 장소가 선택된다.
 */
export function CirclePlaceMarker({
  color,
  size,
  icon,
  label,
  weather,
  ...markerProps
}: CirclePlaceMarkerProps) {
  const border = Math.max(1.5, Math.round(size / 11));
  return (
    <Marker {...markerProps} anchor="left" offset={[-size / 2, 0]}>
      <div
        className="flex items-center"
        style={{ height: size, gap: 4 }}
        data-testid="circle-place-marker"
      >
        <span
          className="flex shrink-0 items-center justify-center rounded-full"
          style={{
            width: size,
            height: size,
            backgroundColor: color,
            border: `${border}px solid #fff`,
            boxShadow: '0 1px 3px rgba(0,0,0,0.35)',
          }}
          data-testid="circle-place-marker-dot"
        >
          {icon}
        </span>
        {(label || weather) && (
          <span
            className="flex max-w-[10.5rem] items-center gap-0.5"
            aria-hidden="true"
            data-testid="circle-place-marker-label"
          >
            {label && (
              <span
                className="min-w-0 truncate text-xs font-semibold leading-tight text-ink"
                style={{ textShadow: LABEL_HALO }}
              >
                {label}
              </span>
            )}
            {weather && <PlaceWeatherGlyph source={weather} decorative />}
          </span>
        )}
      </div>
    </Marker>
  );
}
