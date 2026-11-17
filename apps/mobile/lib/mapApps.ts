import { Linking, Platform } from 'react-native';
import type { MapLink } from '@pinvi/domain';

/** 네이버 지도 앱이 돌아올 앱을 알도록 넘기는 이름 — 앱 번들 id(app.json). */
export const MAP_APP_NAME = 'org.mywire.digitie.pinvi';

/**
 * 지도 앱으로 연다 — 앱 스킴을 먼저 시도하고, 앱이 없어 열리지 않으면 웹 주소로 연다(웹 `openMapLink`의 모바일
 * 대응). Expo Web은 웹 주소만 연다. `canOpenURL`은 iOS에서 스킴 사전 등록이 필요해 쓰지 않고 `openURL`의
 * 거부로 판단한다. 실제로 연 주소를 돌려준다.
 */
export async function openMapLink(
  link: MapLink,
  deps: { openURL?: (url: string) => Promise<unknown>; os?: string } = {},
): Promise<string> {
  const openURL = deps.openURL ?? ((url: string) => Linking.openURL(url));
  const os = deps.os ?? Platform.OS;
  if (link.app && os !== 'web') {
    try {
      await openURL(link.app);
      return link.app;
    } catch {
      // 앱이 없다 — 웹으로.
    }
  }
  await openURL(link.web);
  return link.web;
}
