import { describe, expect, it, vi } from 'vitest';
import { androidIntentUrl, buildMapLinks, detectPlatform, openMapLink } from '@/lib/mapLinks';

const TARGET = { name: '하회마을', lat: 36.5397, lon: 128.5181 };

describe('buildMapLinks', () => {
  it('builds keyless web + app links for naver, kakao and google', () => {
    const [naver, kakao, google] = buildMapLinks(TARGET);
    expect(naver!.web).toBe(
      'https://map.naver.com/p/search/%ED%95%98%ED%9A%8C%EB%A7%88%EC%9D%84?c=128.5181,36.5397,15,0,0,0,dh',
    );
    expect(naver!.app).toMatch(/^nmap:\/\/place\?lat=36\.5397&lng=128\.5181&name=%ED/);
    expect(kakao!.web).toBe(
      'https://map.kakao.com/link/map/%ED%95%98%ED%9A%8C%EB%A7%88%EC%9D%84,36.5397,128.5181',
    );
    expect(kakao!.app).toBe('kakaomap://look?p=36.5397,128.5181');
    expect(google!.web).toBe('https://www.google.com/maps/search/?api=1&query=36.5397,128.5181');
    expect(google!.app).toBeNull();
  });

  it('uses the kakao place page when a numeric place id is known', () => {
    const kakao = buildMapLinks({ ...TARGET, kakaoPlaceId: '8146617' })[1]!;
    expect(kakao.web).toBe('https://place.map.kakao.com/8146617');
    expect(kakao.app).toBe('kakaomap://place?id=8146617');
    expect(buildMapLinks({ ...TARGET, kakaoPlaceId: 'x;y' })[1]!.web).toContain('/link/map/');
  });
});

describe('detectPlatform', () => {
  it('distinguishes android, ios (incl. iPadOS desktop UA) and desktop', () => {
    expect(detectPlatform('Mozilla/5.0 (Linux; Android 14)', 5)).toBe('android');
    expect(detectPlatform('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)', 5)).toBe('ios');
    expect(detectPlatform('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 5)).toBe('ios');
    expect(detectPlatform('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', 0)).toBe('desktop');
    expect(detectPlatform('Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 0)).toBe('desktop');
  });
});

describe('openMapLink', () => {
  const [naver, , google] = buildMapLinks(TARGET);

  it('opens the web page in a new tab on desktop', () => {
    const openTab = vi.fn();
    const navigate = vi.fn();
    openMapLink(naver!, { platform: 'desktop', openTab, navigate });
    expect(openTab).toHaveBeenCalledWith(naver!.web);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('uses an intent URL with a browser fallback on android', () => {
    const navigate = vi.fn();
    const url = openMapLink(naver!, { platform: 'android', navigate });
    expect(url).toBe(androidIntentUrl(naver!));
    expect(url).toMatch(
      /^intent:\/\/place\?lat=.*#Intent;scheme=nmap;package=com\.nhn\.android\.nmap;S\.browser_fallback_url=https%3A%2F%2Fmap\.naver\.com/,
    );
    expect(navigate).toHaveBeenCalledWith(url);
  });

  it('tries the app on iOS and falls back to the web page when the app did not open', () => {
    const navigate = vi.fn();
    let fire: () => void = () => {};
    openMapLink(naver!, {
      platform: 'ios',
      navigate,
      isHidden: () => false,
      setTimer: (fn) => {
        fire = fn;
      },
    });
    expect(navigate).toHaveBeenNthCalledWith(1, naver!.app);
    fire();
    expect(navigate).toHaveBeenNthCalledWith(2, naver!.web);
  });

  it('does not fall back when the app took over the screen', () => {
    const navigate = vi.fn();
    let fire: () => void = () => {};
    openMapLink(naver!, {
      platform: 'ios',
      navigate,
      isHidden: () => true,
      setTimer: (fn) => {
        fire = fn;
      },
    });
    fire();
    expect(navigate).toHaveBeenCalledTimes(1);
  });

  it('opens google (universal link, no app scheme) directly on mobile', () => {
    const navigate = vi.fn();
    openMapLink(google!, { platform: 'ios', navigate });
    expect(navigate).toHaveBeenCalledWith(google!.web);
  });
});
