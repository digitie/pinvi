'use client';

/**
 * maplibre-vworld 동적 import + dev require shim 공통 모듈.
 * SSR 비활성(ssr:false) — 지도 엔진은 브라우저에서만 로드.
 */

import dynamic from 'next/dynamic';
import * as ReactDOMRuntime from 'react-dom';
import * as ReactRuntime from 'react';
import type {
  ClusterLayerProps,
  MakiMarkerProps,
  PopupProps,
  VWorldMapFallbackInfo,
  VWorldMapProps,
} from 'maplibre-vworld';
import 'maplibre-gl/dist/maplibre-gl.css';
import 'maplibre-vworld/style.css';

declare global {
  interface Window {
    require?: (moduleName: string) => unknown;
  }
}

// maplibre-vworld dev 빌드가 UMD `require('react')` 를 호출하는 것을 위한 shim(개발 전용, 멱등).
function installMaplibreVworldDevRequireShim() {
  if (
    typeof window === 'undefined' ||
    process.env.NODE_ENV === 'production' ||
    Reflect.has(window, 'require')
  ) {
    return;
  }
  Object.defineProperty(window, 'require', {
    configurable: true,
    value: (moduleName: string) => {
      if (moduleName === 'react') return ReactRuntime;
      if (moduleName === 'react-dom') return ReactDOMRuntime;
      throw new Error(`Unsupported maplibre-vworld dev require: ${moduleName}`);
    },
  });
}

installMaplibreVworldDevRequireShim();

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

export const VWorldMap = dynamic<VWorldMapProps>(
  () => import('maplibre-vworld').then((module) => module.VWorldMap),
  { ssr: false, loading: () => <MapLoadingSkeleton /> }
);

export const ClusterLayer = dynamic<ClusterLayerProps>(
  () => import('maplibre-vworld').then((module) => module.ClusterLayer),
  { ssr: false }
);

export const MakiMarker = dynamic<MakiMarkerProps>(
  () => import('maplibre-vworld').then((module) => module.MakiMarker),
  { ssr: false }
);

export const Popup = dynamic<PopupProps>(
  () => import('maplibre-vworld').then((module) => module.Popup),
  { ssr: false }
);
