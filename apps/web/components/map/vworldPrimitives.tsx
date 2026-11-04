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
  PinMarkerProps,
  PopupProps,
  RouteLineProps,
  PolygonAreaProps,
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

/**
 * maplibre worker를 정적 파일에서 띄운다(`scripts/copy-maplibre-worker.mjs`가 `predev`/`prebuild`에서
 * `public/maplibre/`로 복사).
 *
 * maplibre 6 ESM은 worker URL을 `import.meta.url`에서 유도하는데, webpack 프로덕션 빌드가 그것을
 * 빌드 머신의 `file:///repo/...` 경로로 굳혀 worker URL이 빈 문자열이 된다("Worker failed to
 * load", 2026-11-02 prod e2e). raster 바탕지도와 HTML 마커는 worker 없이도 그려지지만 worker를
 * 쓰는 GeoJSON/벡터 source는 tile을 하나도 만들지 못한다(kor-travel-map admin 2026-09-18 실측).
 * 지도 인스턴스가 만들어지기 전에 한 번만 설정하면 되므로 지도 엔진을 불러오는 이 동적 import
 * 안에서 부른다 — 저장소에서 지도를 만드는 길은 `VWorldMap` 하나다.
 */
export const MAPLIBRE_WORKER_URL = '/maplibre/maplibre-gl-worker.mjs';

export const VWorldMap = dynamic<VWorldMapViewProps>(
  () =>
    Promise.all([import('maplibre-gl'), import('vworld-map-web')]).then(([maplibre, module]) => {
      // maplibre 기본값처럼 버전을 붙인다 — public 파일은 해시가 없어 프록시 캐시가 옛 worker를 줄 수 있다.
      maplibre.setWorkerUrl(`${MAPLIBRE_WORKER_URL}?v=${maplibre.getVersion()}`);
      return module.VWorldMapView;
    }),
  { ssr: false, loading: () => <MapLoadingSkeleton /> },
);

export const ClusterLayer = dynamic<ClusterLayerProps>(
  () => import('vworld-map-web').then((module) => module.ClusterLayer),
  { ssr: false },
);

export const MakiMarker = dynamic<MakiMarkerProps>(
  () => import('vworld-map-web').then((module) => module.MakiMarker),
  { ssr: false },
);

export const PinMarker = dynamic<PinMarkerProps>(
  () => import('vworld-map-web').then((module) => module.PinMarker),
  { ssr: false },
);

export const Popup = dynamic<PopupProps>(
  () => import('vworld-map-web').then((module) => module.Popup),
  { ssr: false },
);

export const UserLocationMarker = dynamic<UserLocationMarkerProps>(
  () => import('vworld-map-web').then((module) => module.UserLocationMarker),
  { ssr: false },
);

export const WeatherMarker = dynamic<WeatherMarkerProps>(
  () => import('vworld-map-web').then((module) => module.WeatherMarker),
  { ssr: false },
);

export const MapContextMenu = dynamic<MapContextMenuProps>(
  () => import('vworld-map-web').then((module) => module.MapContextMenu),
  { ssr: false },
);

export const RouteLine = dynamic<RouteLineProps>(
  () => import('vworld-map-web').then((module) => module.RouteLine),
  { ssr: false },
);

export const PolygonArea = dynamic<PolygonAreaProps>(
  () => import('vworld-map-web').then((module) => module.PolygonArea),
  { ssr: false },
);
