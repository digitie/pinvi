'use client';

/**
 * vworld-map-web 동적 import 공통 모듈.
 * SSR 비활성(ssr:false) — 지도 엔진은 브라우저에서만 로드.
 */

import 'maplibre-gl/dist/maplibre-gl.css';
import dynamic from 'next/dynamic';
import { useState } from 'react';
import type {
  ClusterLayerProps,
  MakiMarkerProps,
  MapContextMenuProps,
  MarkerProps,
  PinMarkerProps,
  PolygonAreaProps,
  PopupProps,
  RouteLineProps,
  UserLocationMarkerProps,
  VWorldMapFallbackInfo,
  VWorldMapViewProps,
  WeatherMarkerProps,
} from 'vworld-map-web';

export type {
  ClusterPoint,
  MapLibreEvent,
  MapLibreMap,
  MapMouseEvent,
  WeatherCondition,
} from 'vworld-map-web';

/** 높이가 정해진 부모(데스크톱 여행 지도 열 등)는 `minHeightClassName`으로 고정 최소 높이를 푼다(#704). */
const DEFAULT_MAP_MIN_HEIGHT = 'min-h-[360px]';

export function MapLoadingSkeleton({
  minHeightClassName = DEFAULT_MAP_MIN_HEIGHT,
}: { minHeightClassName?: string } = {}) {
  return (
    <div
      className={`flex h-full ${minHeightClassName} items-center justify-center bg-surface-soft text-sm text-muted`}
      data-testid="vworld-map-loading"
    >
      지도 로딩 중
    </div>
  );
}

/**
 * 이 브라우저가 WebGL 컨텍스트를 만들 수 있는지 새 canvas로 확인한다.
 *
 * MapLibre 생성자가 던지는 가장 흔한 이유는 WebGL이 없는 것이다(하드웨어 가속을 끈 브라우저, GPU가 없는
 * 원격 데스크톱·headless Firefox 등 — 2026-11-17 n150 live e2e에서 headless Firefox가
 * `FEATURE_FAILURE_WEBGL_EXHAUSTED_DRIVERS`로 실패했다). 원인이 WebGL이면 키 문제처럼 보이지 않게 따로 알린다.
 */
export function isWebGLAvailable(): boolean {
  if (typeof document === 'undefined') return false;
  try {
    const canvas = document.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'));
  } catch {
    return false;
  }
}

export interface MapFallbackCopy {
  message: string;
  detail: string;
}

/**
 * fallback 사유별 안내 문구. 환경변수 이름은 실제로 키가 비어 있을 때만 보인다 — 엔진 초기화 실패에 키
 * 이름을 보이면 원인을 잘못 짚게 된다(2026-11-17 Firefox live e2e).
 */
export function mapFallbackCopy(info: VWorldMapFallbackInfo, webglAvailable: boolean): MapFallbackCopy {
  if (info.reason === 'missing-api-key') {
    return { message: 'VWorld API 키가 설정되지 않았습니다.', detail: 'NEXT_PUBLIC_VWORLD_API_KEY' };
  }
  if (!webglAvailable) {
    return {
      message: '이 브라우저에서 WebGL을 사용할 수 없어 지도를 표시할 수 없습니다.',
      detail: '브라우저의 하드웨어 가속(WebGL) 설정을 켜거나 다른 브라우저로 열어 주세요.',
    };
  }
  return {
    message: '지도 엔진을 초기화할 수 없습니다.',
    detail: '페이지를 새로 고치거나 잠시 후 다시 시도해 주세요.',
  };
}

export function MapFallback({
  info,
  minHeightClassName = DEFAULT_MAP_MIN_HEIGHT,
}: {
  info: VWorldMapFallbackInfo;
  minHeightClassName?: string;
}) {
  // fallback은 지도 엔진(ssr:false)이 브라우저에서 실패한 뒤에만 그려지므로 여기서 한 번 확인하면 된다.
  const [webglAvailable] = useState(() => info.reason !== 'map-init-error' || isWebGLAvailable());
  const { message, detail } = mapFallbackCopy(info, webglAvailable);
  const reason = info.reason === 'map-init-error' && !webglAvailable ? 'webgl-unavailable' : info.reason;
  return (
    <div
      className={`flex h-full ${minHeightClassName} items-center justify-center bg-surface-soft px-6 text-center`}
      data-testid="vworld-map-fallback"
      data-fallback-reason={reason}
    >
      <div className="max-w-sm space-y-2">
        <p className="text-base font-semibold text-ink">{message}</p>
        <p className="text-sm text-muted">{detail}</p>
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
const MAPLIBRE_WORKER_URL = '/maplibre/maplibre-gl-worker.mjs';

const DynamicVWorldMap = dynamic<VWorldMapViewProps>(
  () =>
    Promise.all([import('maplibre-gl'), import('vworld-map-web')]).then(([maplibre, module]) => {
      // maplibre 기본값처럼 버전을 붙인다 — public 파일은 해시가 없어 프록시 캐시가 옛 worker를 줄 수 있다.
      maplibre.setWorkerUrl(`${MAPLIBRE_WORKER_URL}?v=${maplibre.getVersion()}`);
      return module.VWorldMapView;
    }),
  { ssr: false, loading: () => <MapLoadingSkeleton /> },
);

const DynamicClusterLayer = dynamic<ClusterLayerProps>(
  () => import('vworld-map-web').then((module) => module.ClusterLayer),
  { ssr: false },
);

const DynamicMakiMarker = dynamic<MakiMarkerProps>(
  () => import('vworld-map-web').then((module) => module.MakiMarker),
  { ssr: false },
);

const DynamicMarker = dynamic<MarkerProps>(
  () => import('vworld-map-web').then((module) => module.Marker),
  { ssr: false },
);

const DynamicPinMarker = dynamic<PinMarkerProps>(
  () => import('vworld-map-web').then((module) => module.PinMarker),
  { ssr: false },
);

const VWorldPopup = dynamic<PopupProps>(
  () => import('vworld-map-web').then((module) => module.Popup),
  { ssr: false },
);

/** 앱 컨트롤(z10)보다 선택 popup이 위에 오도록 애플리케이션 계층을 지정한다. */
export function Popup(props: PopupProps) {
  return (
    <VWorldPopup
      {...props}
      className={['pinvi-map-popup', props.className].filter(Boolean).join(' ')}
    />
  );
}

const DynamicUserLocationMarker = dynamic<UserLocationMarkerProps>(
  () => import('vworld-map-web').then((module) => module.UserLocationMarker),
  { ssr: false },
);

const DynamicWeatherMarker = dynamic<WeatherMarkerProps>(
  () => import('vworld-map-web').then((module) => module.WeatherMarker),
  { ssr: false },
);

const DynamicMapContextMenu = dynamic<MapContextMenuProps>(
  () => import('vworld-map-web').then((module) => module.MapContextMenu),
  { ssr: false },
);

const DynamicRouteLine = dynamic<RouteLineProps>(
  () => import('vworld-map-web').then((module) => module.RouteLine),
  { ssr: false },
);

const DynamicPolygonArea = dynamic<PolygonAreaProps>(
  () => import('vworld-map-web').then((module) => module.PolygonArea),
  { ssr: false },
);

export function VWorldMap(props: VWorldMapViewProps) {
  return <DynamicVWorldMap {...props} />;
}

export function ClusterLayer(props: ClusterLayerProps) {
  return <DynamicClusterLayer {...props} />;
}

export function MakiMarker(props: MakiMarkerProps) {
  return <DynamicMakiMarker {...props} />;
}

/** children을 그대로 그리는 기본 마커(원형 장소 마커처럼 모양을 앱이 정할 때). */
export function Marker(props: MarkerProps) {
  return <DynamicMarker {...props} />;
}

export function PinMarker(props: PinMarkerProps) {
  return <DynamicPinMarker {...props} />;
}

export function UserLocationMarker(props: UserLocationMarkerProps) {
  return <DynamicUserLocationMarker {...props} />;
}

export function WeatherMarker(props: WeatherMarkerProps) {
  return <DynamicWeatherMarker {...props} />;
}

export function MapContextMenu(props: MapContextMenuProps) {
  return <DynamicMapContextMenu {...props} />;
}

export function RouteLine(props: RouteLineProps) {
  return <DynamicRouteLine {...props} />;
}

export function PolygonArea(props: PolygonAreaProps) {
  return <DynamicPolygonArea {...props} />;
}
