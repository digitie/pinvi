/**
 * 장소를 네이버·카카오·구글 지도에서 여는 링크 — 웹·모바일 공용(여는 방법은 각 앱이 정한다).
 *
 * 세 서비스 모두 공개 URL 규약만 쓴다 — 링크를 만드는 데 API 키가 필요 없다(서버·concierge 조회 불필요).
 * - 네이버 지도: 웹 `map.naver.com/p/search/{이름}?c={lon},{lat},…`, 앱 `nmap://place?lat=&lng=&name=&appname=`
 *   (NAVER Maps URL Scheme). `appname`은 웹은 호스트 이름, 모바일은 앱 번들 id다.
 * - 카카오맵: 웹 `map.kakao.com/link/map/{이름},{lat},{lon}`(카카오맵 URL 링크), 장소 id가 있으면
 *   `place.map.kakao.com/{id}`. 앱 `kakaomap://look?p={lat},{lon}` / `kakaomap://place?id=`.
 * - 구글 지도: Maps URLs `google.com/maps/search/?api=1&query={lat},{lon}` — 모바일에서는 이 https 주소가
 *   설치된 앱을 바로 연다(유니버설/앱 링크)라 별도 앱 스킴이 없다.
 */

export type MapProvider = 'naver' | 'kakao' | 'google';

export interface MapLinkTarget {
  name: string;
  lat: number;
  lon: number;
  /** 카카오 장소 id(카카오 검색으로 추가한 장소의 external_ref). */
  kakaoPlaceId?: string | null;
}

export interface MapLink {
  provider: MapProvider;
  label: string;
  web: string;
  /** 앱 스킴. 없으면 웹 주소만 쓴다. */
  app: string | null;
  /** Android 앱 패키지(intent fallback용). */
  androidPackage: string | null;
}

const enc = encodeURIComponent;

export function buildMapLinks(target: MapLinkTarget, { appName }: { appName: string }): MapLink[] {
  const { name, lat, lon } = target;
  const kakaoId =
    target.kakaoPlaceId && /^\d+$/.test(target.kakaoPlaceId) ? target.kakaoPlaceId : null;
  return [
    {
      provider: 'naver',
      label: '네이버 지도',
      web: `https://map.naver.com/p/search/${enc(name)}?c=${lon},${lat},15,0,0,0,dh`,
      app: `nmap://place?lat=${lat}&lng=${lon}&name=${enc(name)}&appname=${enc(appName)}`,
      androidPackage: 'com.nhn.android.nmap',
    },
    {
      provider: 'kakao',
      label: '카카오맵',
      web: kakaoId
        ? `https://place.map.kakao.com/${kakaoId}`
        : `https://map.kakao.com/link/map/${enc(name)},${lat},${lon}`,
      app: kakaoId ? `kakaomap://place?id=${kakaoId}` : `kakaomap://look?p=${lat},${lon}`,
      androidPackage: 'net.daum.android.map',
    },
    {
      provider: 'google',
      label: '구글 지도',
      web: `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`,
      app: null,
      androidPackage: null,
    },
  ];
}
