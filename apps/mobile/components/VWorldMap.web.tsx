import { lazy, Suspense, useSyncExternalStore } from 'react';
import { View } from 'react-native';
import { Muted } from './ui';
import type { PlatformVWorldMapProps } from './VWorldMap.types';

const ClientMap = lazy(() =>
  import('./VWorldMapWeb').then((loaded) => ({ default: loaded.WebVWorldMap })),
);
function subscribeBrowser() {
  return () => undefined;
}
function browserReady() {
  return true;
}
function serverReady() {
  return false;
}

/** SSR에서는 엔진 모듈을 평가하지 않는다. native package는 타입으로만 참조한다. */
export function VWorldMapView(props: PlatformVWorldMapProps) {
  const ready = useSyncExternalStore(subscribeBrowser, browserReady, serverReady);
  const placeholder = (
    <View style={[{ flex: 1 }, props.style]}>
      <Muted>지도를 준비하는 중…</Muted>
    </View>
  );
  if (!ready) return placeholder;
  return (
    <Suspense fallback={placeholder}>
      <ClientMap {...props} />
    </Suspense>
  );
}
export type { VWorldMapHandle } from './VWorldMap.types';
