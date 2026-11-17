import { describe, expect, it, vi } from 'vitest';
import { buildMapLinks } from '@pinvi/domain';
import { MAP_APP_NAME, openMapLink } from '../lib/mapApps';

const [naver, kakao, google] = buildMapLinks(
  { name: '경포대', lat: 37.8, lon: 128.9 },
  { appName: MAP_APP_NAME },
);

describe('지도 앱 열기(모바일)', () => {
  it('앱 스킴을 먼저 열고(네이버 appname = 앱 번들 id), 열리면 웹은 열지 않는다', async () => {
    const openURL = vi.fn(async (_url: string) => true);
    expect(await openMapLink(naver!, { openURL, os: 'ios' })).toMatch(/^nmap:\/\/place\?/);
    expect(naver!.app).toContain(`appname=${encodeURIComponent(MAP_APP_NAME)}`);
    expect(openURL).toHaveBeenCalledTimes(1);
  });

  it('앱이 없어 열리지 않으면 웹 주소로 연다', async () => {
    const openURL = vi.fn(async (url: string) => {
      if (url.startsWith('kakaomap://')) throw new Error('no app');
      return true;
    });
    expect(await openMapLink(kakao!, { openURL, os: 'android' })).toBe(kakao!.web);
    expect(openURL.mock.calls.map(([url]) => url)).toEqual([kakao!.app, kakao!.web]);
  });

  it('앱 스킴이 없는 구글 지도와 Expo Web은 웹 주소만 연다', async () => {
    const openURL = vi.fn(async (_url: string) => true);
    expect(await openMapLink(google!, { openURL, os: 'ios' })).toBe(google!.web);
    expect(await openMapLink(naver!, { openURL, os: 'web' })).toBe(naver!.web);
    expect(openURL.mock.calls.map(([url]) => url)).toEqual([google!.web, naver!.web]);
  });
});
