import type { AddProtocolAction } from 'maplibre-gl';

/**
 * vworld-map-web 1.0.3 `vworld://` 타일 protocol 대체(PC 바탕지도 누락, 2026-11-16).
 *
 * 라이브러리 handler는 `new URL('vworld://…')`의 `protocol`을 `'https:'`로 바꾼 뒤 fetch한다. WHATWG URL
 * 표준은 비특수 스킴(`vworld:`)→특수 스킴(`https:`) 전환을 **무시**하므로 Firefox·Safari(WebKit)는
 * `vworld://`를 그대로 fetch해 모든 바탕지도 타일이 실패하고 회색 fallback만 그린다(데스크톱 Firefox 실측:
 * "CORS request not http", api.vworld.kr 요청 0건). Chrome·Edge는 표준과 달리 바꿔 줘서 드러나지 않았고,
 * live e2e 두 프로젝트(desktop·mobile)가 모두 Chromium이라 잡히지 않았다.
 *
 * 스킴은 문자열로 갈아 끼우고, 나머지(커버리지 밖 XML→fallback, `vworld-tile-error` 이벤트)는 라이브러리와
 * 같다. 정본 수정 자리는 maplibre-vworld-react `packages/vworld-map-web/src/vworld.ts` — 고친 판을 vendor하면
 * 이 파일과 `vworldPrimitives.tsx`의 덮어쓰기를 지운다.
 */
const SCHEME = 'vworld://';

export interface VWorldTileRequest {
  httpsUrl: string;
  fallbackUrl: string | null;
  label: string | null;
  mapId: string | null;
}

export function vworldTileRequest(url: string): VWorldTileRequest {
  const urlObj = new URL(url.startsWith(SCHEME) ? `https://${url.slice(SCHEME.length)}` : url);
  const fallbackUrl = urlObj.searchParams.get('fallback');
  const label = urlObj.searchParams.get('label');
  const mapId = urlObj.searchParams.get('mapId');
  for (const key of ['fallback', 'label', 'mapId']) urlObj.searchParams.delete(key);
  return { httpsUrl: urlObj.toString(), fallbackUrl, label, mapId };
}

const FALLBACK_CACHE_LIMIT = 32;
const fallbackCache = new Map<string, ArrayBuffer>();

function escapeXml(text: string): string {
  return text.replace(/[<>&"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

async function fallbackImage(imageUrl: string | null, label: string | null): Promise<ArrayBuffer> {
  const key = `${imageUrl ?? ''}|${label ?? ''}`;
  const cached = fallbackCache.get(key);
  if (cached) return cached;
  let data: ArrayBuffer | null = null;
  if (imageUrl) {
    try {
      const res = await fetch(imageUrl);
      if (res.ok) data = await res.arrayBuffer();
    } catch {
      // 기본 SVG로 내려간다.
    }
  }
  if (data === null) {
    const text = escapeXml(label || '지원하지 않는 타일');
    const svg = `<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg"><rect width="256" height="256" fill="#f5f5f5"/><text x="128" y="155" font-family="sans-serif" font-size="14" fill="#999" text-anchor="middle">${text}</text></svg>`;
    data = await new Blob([svg], { type: 'image/svg+xml' }).arrayBuffer();
  }
  if (fallbackCache.size >= FALLBACK_CACHE_LIMIT) {
    const oldest = fallbackCache.keys().next().value;
    if (oldest !== undefined) fallbackCache.delete(oldest);
  }
  fallbackCache.set(key, data);
  return data;
}

export const vworldTileProtocol: AddProtocolAction = async (params, abortController) => {
  const { httpsUrl, fallbackUrl, label, mapId } = vworldTileRequest(params.url);
  try {
    const response = await fetch(httpsUrl, { signal: abortController.signal });
    if (!response.ok) throw new Error(`HTTP error ${response.status}`);
    const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
    if (contentType.includes('xml')) {
      // VWorld는 국내 커버리지 밖 타일에 200 + XML OWS 예외를 준다 — 그것만 정상 fallback이다.
      const body = await response.text();
      if (body.includes('ExceptionReport') && body.includes('서비스 제공영역이 아닙니다')) {
        return { data: await fallbackImage(fallbackUrl, label) };
      }
      throw new Error('VWorld returned an unexpected XML tile response');
    }
    return { data: await response.arrayBuffer() };
  } catch (error) {
    if (abortController.signal.aborted) throw error;
    window.dispatchEvent(
      new CustomEvent('vworld-tile-error', { detail: { url: httpsUrl, error, mapId } }),
    );
    return { data: await fallbackImage(fallbackUrl, label) };
  }
};
