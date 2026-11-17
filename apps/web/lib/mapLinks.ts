/**
 * 장소를 네이버·카카오·구글 지도에서 여는 링크(링크 규약은 `@pinvi/domain` `mapLinks`).
 *
 * 세 서비스 모두 공개 URL 규약만 쓴다 — 링크를 만드는 데 API 키가 필요 없다(서버·concierge 조회 불필요).
 * - 네이버 지도: 웹 `map.naver.com/p/search/{이름}?c={lon},{lat},…`, 앱 `nmap://place?lat=&lng=&name=&appname=`
 *   (NAVER Maps URL Scheme).
 * - 카카오맵: 웹 `map.kakao.com/link/map/{이름},{lat},{lon}`(카카오맵 URL 링크), 장소 id가 있으면
 *   `place.map.kakao.com/{id}`. 앱 `kakaomap://look?p={lat},{lon}` / `kakaomap://place?id=`.
 * - 구글 지도: Maps URLs `google.com/maps/search/?api=1&query={lat},{lon}` — 모바일에서는 이 https 주소가
 *   설치된 앱을 바로 연다(유니버설/앱 링크)라 별도 앱 스킴이 없다.
 *
 * PC는 웹 주소를 새 탭으로 연다. 모바일은 앱을 먼저 시도하고, 앱이 없으면 웹으로 넘어간다 —
 * Android는 `intent://…;S.browser_fallback_url=` 로 브라우저가 대신 처리하고, iOS는 앱 스킴을 연 뒤
 * 화면이 그대로 보이면(앱이 열리지 않으면) 잠시 뒤 웹 주소로 이동한다.
 */

import {
  buildMapLinks as buildSharedMapLinks,
  type MapLink,
  type MapLinkTarget,
} from '@pinvi/domain';

export type { MapLink, MapLinkTarget, MapProvider } from '@pinvi/domain';

const enc = encodeURIComponent;

function appName(): string {
  return typeof window !== 'undefined' ? window.location.hostname || 'pinvi' : 'pinvi';
}

/** 링크 규약은 `@pinvi/domain` `buildMapLinks`(모바일과 공용) — 웹은 네이버 `appname`에 호스트 이름을 쓴다. */
export function buildMapLinks(target: MapLinkTarget): MapLink[] {
  return buildSharedMapLinks(target, { appName: appName() });
}

export type DevicePlatform = 'android' | 'ios' | 'desktop';

export function detectPlatform(
  userAgent: string = typeof navigator !== 'undefined' ? navigator.userAgent : '',
  maxTouchPoints: number = typeof navigator !== 'undefined' ? navigator.maxTouchPoints : 0,
): DevicePlatform {
  if (/Android/i.test(userAgent)) return 'android';
  if (/iPhone|iPad|iPod/i.test(userAgent)) return 'ios';
  // iPadOS 13+ 사파리는 데스크톱 UA(Macintosh)를 보낸다 — 터치 지원으로 구분한다.
  if (/Macintosh/i.test(userAgent) && maxTouchPoints > 1) return 'ios';
  return 'desktop';
}

/** Android intent URL — 앱이 없으면 브라우저가 `browser_fallback_url`(웹)로 간다. */
export function androidIntentUrl(link: MapLink): string | null {
  if (!link.app || !link.androidPackage) return null;
  const match = /^([a-z][a-z0-9+.-]*):\/\/(.*)$/i.exec(link.app);
  if (!match) return null;
  const [, scheme, rest] = match;
  return `intent://${rest}#Intent;scheme=${scheme};package=${link.androidPackage};S.browser_fallback_url=${enc(link.web)};end`;
}

export interface OpenDeps {
  platform?: DevicePlatform;
  navigate?: (url: string) => void;
  openTab?: (url: string) => void;
  /** 앱이 열렸는지(페이지가 가려졌는지) — 기본은 document.visibilityState. */
  isHidden?: () => boolean;
  setTimer?: (fn: () => void, ms: number) => unknown;
}

const IOS_FALLBACK_MS = 1500;

/** 링크를 연다. 반환값은 실제로 시도한 주소(테스트·로그용). */
export function openMapLink(link: MapLink, deps: OpenDeps = {}): string {
  const platform = deps.platform ?? detectPlatform();
  const navigate = deps.navigate ?? ((url: string) => window.location.assign(url));
  const openTab =
    deps.openTab ?? ((url: string) => void window.open(url, '_blank', 'noopener,noreferrer'));
  if (platform === 'desktop' || !link.app) {
    if (platform === 'desktop') openTab(link.web);
    else navigate(link.web);
    return link.web;
  }
  if (platform === 'android') {
    const intent = androidIntentUrl(link) ?? link.web;
    navigate(intent);
    return intent;
  }
  const isHidden = deps.isHidden ?? (() => document.visibilityState === 'hidden');
  const setTimer = deps.setTimer ?? ((fn: () => void, ms: number) => window.setTimeout(fn, ms));
  navigate(link.app);
  setTimer(() => {
    if (!isHidden()) navigate(link.web);
  }, IOS_FALLBACK_MS);
  return link.app;
}
