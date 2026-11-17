import { describe, expect, it } from 'vitest';
import { ApiError } from '@pinvi/api-client';
import type { PoiPlaceDetails } from '@pinvi/schemas';
import { buildMapLinks } from './mapLinks';
import {
  hasAnyPlaceDetail,
  placeDetailsRefreshErrorMessage,
  placeDetailsSourceLine,
  telHref,
  todayHoursLine,
} from './placeDetails';
import { canEditTrip } from './tripPermissions';

const details = (patch: Partial<PoiPlaceDetails> = {}): PoiPlaceDetails =>
  ({
    opening_hours: [],
    closed_days: null,
    phone: null,
    website: null,
    sources: {},
    fetched_at: null,
    ...patch,
  }) as PoiPlaceDetails;

describe('장소 정보 공용 문구', () => {
  it('오늘(KST) 영업시간 — 한 줄이면 그 줄, 요일별이면 오늘 요일 줄', () => {
    // 2026-11-17은 화요일(KST).
    const now = Date.parse('2026-11-17T03:00:00Z');
    expect(todayHoursLine([], now)).toBeNull();
    expect(todayHoursLine(['매일 09:00~18:00'], now)).toBe('매일 09:00~18:00');
    expect(todayHoursLine(['월요일 휴무', '화요일 10:00~20:00'], now)).toBe('화요일 10:00~20:00');
  });

  it('보일 정보가 있는가·출처 줄·전화 주소', () => {
    expect(hasAnyPlaceDetail(null)).toBe(false);
    expect(hasAnyPlaceDetail(details())).toBe(false);
    expect(hasAnyPlaceDetail(details({ phone: '033-1' }))).toBe(true);
    expect(
      placeDetailsSourceLine(
        details({ sources: { phone: 'kor_travel_map' }, fetched_at: '2026-11-16T20:00:00Z' }),
      ),
    ).toBe('출처: 공공데이터(한국 여행 지도) · 2026-11-17 확인');
    expect(telHref('033-640 (5000)')).toBe('tel:0336405000');
  });

  it('다시 읽어오기 실패 문구 — 429 대기, 403 편집 권한', () => {
    expect(
      placeDetailsRefreshErrorMessage(new ApiError('RATE_LIMITED', 'x', 429, undefined, 30)),
    ).toBe('30초 뒤에 다시 읽어올 수 있습니다.');
    expect(placeDetailsRefreshErrorMessage(new ApiError('PERMISSION_DENIED', 'x', 403))).toContain(
      '편집할 수 있는 사람만',
    );
    expect(placeDetailsRefreshErrorMessage(new Error('x'))).toContain('다시 읽어오지 못했습니다');
  });
});

describe('지도 앱 링크(공용 규약)', () => {
  it('네이버 appname은 호출하는 앱이 정하고, 카카오 장소 id는 숫자만 쓴다', () => {
    const [naver, kakao, google] = buildMapLinks(
      { name: '경포대', lat: 37.8, lon: 128.9, kakaoPlaceId: '123' },
      { appName: 'org.example.app' },
    );
    expect(naver!.app).toBe(
      `nmap://place?lat=37.8&lng=128.9&name=${encodeURIComponent('경포대')}&appname=org.example.app`,
    );
    expect(kakao!.web).toBe('https://place.map.kakao.com/123');
    expect(google!.app).toBeNull();
    expect(
      buildMapLinks({ name: 'x', lat: 1, lon: 2, kakaoPlaceId: '1;2' }, { appName: 'a' })[1]!.app,
    ).toBe('kakaomap://look?p=1,2');
  });
});

describe('canEditTrip', () => {
  const view = {
    trip: { owner_user_id: 'owner' },
    companions: [
      { user_id: 'editor', role: 'editor' },
      { user_id: 'viewer', role: 'viewer' },
      { user_id: 'co', role: 'co_owner' },
    ],
  } as unknown as Parameters<typeof canEditTrip>[0];

  it('소유자·편집자·공동 소유자만, 보기 전용·모르는 사용자는 아니다', () => {
    expect(canEditTrip(view, 'owner')).toBe(true);
    expect(canEditTrip(view, 'editor')).toBe(true);
    expect(canEditTrip(view, 'co')).toBe(true);
    expect(canEditTrip(view, 'viewer')).toBe(false);
    expect(canEditTrip(view, 'stranger')).toBe(false);
    expect(canEditTrip(view, null)).toBe(false);
  });
});
