'use client';

import { LocationConsentDialog } from '@/components/map/LocationConsentDialog';
import type { MapLibreMap } from '@/components/map/vworldPrimitives';
import { apiClient } from '@/lib/api';
import { getLocationConsentState, setLocationConsentGranted } from '@/lib/locationConsent';
import { useLiftAboveObstacle } from '@/lib/useLiftAboveObstacle';
import { useLocationFollow, type LocationFollowMode } from '@/lib/useLocationFollow';
import { ApiError, userApi } from '@pinvi/api-client';
import { locationConsentItems } from '@pinvi/domain';
import { LocateFixed, Locate, Navigation } from 'lucide-react';
import { createElement, useCallback, useEffect, useRef, useState } from 'react';

const MODE_LABEL: Record<LocationFollowMode, string> = {
  off: '내 위치로 이동',
  locating: '내 위치 찾는 중',
  follow: '내 위치를 따라가는 중',
  tracking: '내 위치로 돌아가기',
};

/**
 * 지도 "내 위치" 컨트롤 상태 — 버튼·동의 다이얼로그·안내는 `MyLocationControl`이, 파란 점은 호출부가
 * 지도 안에 `UserLocationMarker`로 그린다(마커는 지도 컨텍스트 안에서만 그릴 수 있다).
 */
export function useMyLocationControl(getMap: () => MapLibreMap | null) {
  const [consentOpen, setConsentOpen] = useState(false);
  const [consentSaving, setConsentSaving] = useState(false);
  const [consentError, setConsentError] = useState<string | null>(null);
  // 동의 직후 측위 시작은 follow 훅이 준다 — 훅보다 먼저 만든 콜백이 늦게 붙는 값을 읽게 ref로 둔다.
  const startRef = useRef<() => void>(() => {});

  const ensureConsent = useCallback(async () => {
    // 세션 캐시에 기대지 않는다 — 다른 탭에서의 철회도 즉시 반영(위치정보법 제16조, FeatureMapView와 같은 규칙).
    const state = await getLocationConsentState({ force: true });
    if (state === 'granted') return true;
    setConsentError(null);
    setConsentOpen(true);
    return false;
  }, []);

  const follow = useLocationFollow({ getMap, ensureConsent });
  const { startWatch } = follow;
  useEffect(() => {
    startRef.current = startWatch;
  }, [startWatch]);

  const agree = useCallback(async () => {
    setConsentSaving(true);
    setConsentError(null);
    try {
      await userApi(apiClient).putConsents(locationConsentItems());
      setLocationConsentGranted();
      setConsentOpen(false);
      startRef.current();
    } catch (err) {
      setConsentError(err instanceof ApiError ? err.message : '동의 저장에 실패했습니다.');
    } finally {
      setConsentSaving(false);
    }
  }, []);

  return {
    ...follow,
    consentOpen,
    consentSaving,
    consentError,
    agree,
    cancelConsent: () => setConsentOpen(false),
  };
}

export type MyLocationControlState = ReturnType<typeof useMyLocationControl>;

/**
 * 구글·네이버 지도식 "내 위치" 버튼. 누르면 현재 위치로 옮기고 따라가기를 켠다. 지도를 손으로 끌면
 * 따라가기만 꺼지고(아이콘이 빈 과녁으로 바뀐다) 다시 누르면 돌아온다.
 */
export function MyLocationControl({
  state,
  className = 'absolute bottom-10 right-3 z-10',
  hidden = false,
}: {
  state: MyLocationControlState;
  className?: string;
  /** 버튼을 두지 않는 화면(비로그인 공유 등). 상태 훅은 호출부가 늘 부른다. */
  hidden?: boolean;
}) {
  const { mode } = state;
  // 아래에서 올라온 장소 패널(`data-map-location-avoid`)이 있으면 그 위로 올린다 — 패널에 가려지지 않게.
  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  const lift = useLiftAboveObstacle(root);
  if (hidden) return null;
  const icon = mode === 'follow' ? Navigation : mode === 'tracking' ? Locate : LocateFixed;
  return (
    <>
      <div
        ref={setRoot}
        className={`pointer-events-none flex flex-col items-end gap-1 ${className}`}
        style={lift != null ? { bottom: lift } : undefined}
        data-map-overlay=""
        data-lifted={lift != null ? 'true' : 'false'}
        data-testid="map-my-location-control"
      >
        {state.error && (
          <p
            role="status"
            className="pointer-events-auto max-w-[16rem] rounded-sm bg-canvas/95 px-2 py-1 text-xs text-body shadow-card"
            data-testid="my-location-error"
          >
            {state.error}
          </p>
        )}
        <button
          type="button"
          onClick={() => void state.activate()}
          aria-label={MODE_LABEL[mode]}
          title={MODE_LABEL[mode]}
          aria-pressed={mode === 'follow'}
          aria-busy={mode === 'locating'}
          data-testid="map-my-location"
          data-follow-mode={mode}
          className={`focus-ring pointer-events-auto flex size-11 items-center justify-center rounded-full border border-hairline bg-canvas shadow-card hover:bg-surface-soft ${
            mode === 'follow' ? 'text-primary' : 'text-ink'
          }`}
        >
          {createElement(icon, {
            className: `h-5 w-5 ${mode === 'locating' ? 'animate-pulse' : ''}`,
            'aria-hidden': true,
            ...(mode === 'follow' ? { fill: 'currentColor' } : {}),
          })}
        </button>
      </div>
      <LocationConsentDialog
        open={state.consentOpen}
        saving={state.consentSaving}
        error={state.consentError}
        onAgree={() => void state.agree()}
        onCancel={state.cancelConsent}
      />
    </>
  );
}
