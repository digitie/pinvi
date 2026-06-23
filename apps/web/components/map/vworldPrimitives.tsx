'use client';

/**
 * vworld-map-web 동적 import 공통 모듈.
 * SSR 비활성(ssr:false) — 지도 엔진은 브라우저에서만 로드.
 */

import dynamic from 'next/dynamic';
import type {
  ClusterLayerProps,
  MakiMarkerProps,
  MapContextMenuProps,
  PopupProps,
  UserLocationMarkerProps,
  VWorldMapFallbackInfo,
  VWorldMapViewProps,
  WeatherMarkerProps,
} from 'vworld-map-web';
import 'maplibre-gl/dist/maplibre-gl.css';

export type {
  ClusterPoint,
  MapLibreEvent,
  MapLibreMap,
  MapMouseEvent,
  WeatherCondition,
} from 'vworld-map-web';

export function MapLoadingSkeleton() {
  return (
    <div
      className="flex h-full min-h-[360px] items-center justify-center bg-surface-soft text-sm text-muted"
      data-testid="vworld-map-loading"
    >
      지도 로딩 중
    </div>
  );
}

export function MapFallback({ info }: { info: VWorldMapFallbackInfo }) {
  const message =
    info.reason === 'missing-api-key'
      ? 'VWorld API 키가 설정되지 않았습니다.'
      : '지도 엔진을 초기화할 수 없습니다.';
  return (
    <div
      className="flex h-full min-h-[360px] items-center justify-center bg-surface-soft px-6 text-center"
      data-testid="vworld-map-fallback"
    >
      <div className="max-w-sm space-y-2">
        <p className="text-base font-semibold text-ink">{message}</p>
        <p className="text-sm text-muted">NEXT_PUBLIC_VWORLD_API_KEY</p>
      </div>
    </div>
  );
}

export const VWorldMap = dynamic<VWorldMapViewProps>(
  () => import('vworld-map-web').then((module) => module.VWorldMapView),
  { ssr: false, loading: () => <MapLoadingSkeleton /> }
);

export const ClusterLayer = dynamic<ClusterLayerProps>(
  () => import('vworld-map-web').then((module) => module.ClusterLayer),
  { ssr: false }
);

export const MakiMarker = dynamic<MakiMarkerProps>(
  () => import('vworld-map-web').then((module) => module.MakiMarker),
  { ssr: false }
);

export const Popup = dynamic<PopupProps>(
  () => import('vworld-map-web').then((module) => module.Popup),
  { ssr: false }
);

export const UserLocationMarker = dynamic<UserLocationMarkerProps>(
  () => import('vworld-map-web').then((module) => module.UserLocationMarker),
  { ssr: false }
);

export const WeatherMarker = dynamic<WeatherMarkerProps>(
  () => import('vworld-map-web').then((module) => module.WeatherMarker),
  { ssr: false }
);

export const MapContextMenu = dynamic<MapContextMenuProps>(
  () => import('vworld-map-web').then((module) => module.MapContextMenu),
  { ssr: false }
);
