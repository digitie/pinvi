import type { VWorldMapFallbackInfo } from 'vworld-map-web';

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
