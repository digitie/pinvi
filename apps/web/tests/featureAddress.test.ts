import { describe, expect, it } from 'vitest';
import { addressLine } from '@/lib/featureAddress';

// 2026-11-02 prod e2e — 지도 팝업이 Map 주소 dict의 첫 문자열(`admin`="김삿갓면")만 보였다.
// 서버 detail-card `address_line`과 같은 규칙을 쓴다.
describe('addressLine', () => {
  it('도로명이 없으면 법정동 주소(legal)를 쓴다', () => {
    expect(
      addressLine({
        address: {
          road: null,
          admin: '김삿갓면',
          legal: '강원특별자치도 영월군 김삿갓면',
          zipcode: null,
          bjd_code: '5175032500',
        },
      }),
    ).toBe('강원특별자치도 영월군 김삿갓면');
  });

  it('legal도 없으면 "시도 시군구 읍면동"을 만들고 코드·우편번호는 쓰지 않는다', () => {
    expect(
      addressLine({
        address: {
          road: null,
          legal: null,
          admin: '풍천면',
          zipcode: '36760',
          bjd_code: '4717034033',
          sido_name: '경상북도',
          sigungu_name: '안동시',
        },
      }),
    ).toBe('경상북도 안동시 풍천면');
    expect(addressLine({ address: { zipcode: '36760', bjd_code: '4717034033' } })).toBeNull();
  });

  it('admin에 이미 시도·시군구가 있으면 반복하지 않는다', () => {
    expect(
      addressLine({
        address: {
          admin: '부산광역시 해운대구',
          sido_name: '부산광역시',
          sigungu_name: '해운대구',
        },
      }),
    ).toBe('부산광역시 해운대구');
  });

  it('도로명 주소가 있으면 그것이 먼저다', () => {
    expect(
      addressLine({ address: { road: '경상북도 안동시 도산서원길 154', legal: '토계리 679-2' } }),
    ).toBe('경상북도 안동시 도산서원길 154');
  });
});
