import { describe, expect, it } from 'vitest';
import type { SourceIntroduction } from '@pinvi/schemas';
import {
  introductionHasContent,
  introductionNeedsCollapse,
  isKoglLicenseUrl,
  isTourapiImageUrl,
  visibleIntroductionImages,
} from './sourceIntroduction';

const IMAGE = 'https://tong.visitkorea.or.kr/cms/resource/a.jpg';

function intro(over: Partial<SourceIntroduction> = {}): SourceIntroduction {
  return {
    provider: 'tourapi',
    attribution: '한국관광공사',
    overview: null,
    images: [{ url: IMAGE, alt: 'a', kogl_type: 3, no_derivatives: true }],
    kogl_type: 3,
    license_label: '공공누리 제3유형: 출처표시 + 변경금지',
    license_url: 'https://www.kogl.or.kr/info/licenseType3.do',
    ...over,
  };
}

describe('sourceIntroduction', () => {
  it('이미지 URL은 TourAPI 호스트 https만 받는다', () => {
    expect(isTourapiImageUrl(IMAGE)).toBe(true);
    expect(isTourapiImageUrl('http://tong.visitkorea.or.kr/a.jpg')).toBe(false);
    expect(isTourapiImageUrl('https://evil.example/a.jpg')).toBe(false);
    expect(isTourapiImageUrl('https://visitkorea.or.kr.evil.example/a.jpg')).toBe(false);
    expect(isTourapiImageUrl('https://u:p@tong.visitkorea.or.kr/a.jpg')).toBe(false);
    expect(isTourapiImageUrl('javascript:alert(1)')).toBe(false);
    expect(isTourapiImageUrl('not a url')).toBe(false);
  });

  it('공공누리 링크는 kogl.or.kr https만 받는다', () => {
    expect(isKoglLicenseUrl('https://www.kogl.or.kr/info/licenseType1.do')).toBe(true);
    expect(isKoglLicenseUrl('https://www.kogl.or.kr.evil.example/')).toBe(false);
    expect(isKoglLicenseUrl('intent://x')).toBe(false);
    expect(isKoglLicenseUrl(null)).toBe(false);
  });

  it('깨진 이미지와 허용 밖 이미지는 보이는 이미지에서 빠진다', () => {
    const data = intro({
      images: [
        { url: IMAGE, alt: 'a', kogl_type: 3, no_derivatives: true },
        { url: 'https://evil.example/b.jpg', alt: 'b', kogl_type: 1, no_derivatives: false },
      ],
    });
    expect(visibleIntroductionImages(data, new Set()).map((i) => i.url)).toEqual([IMAGE]);
    expect(visibleIntroductionImages(data, new Set([IMAGE]))).toEqual([]);
  });

  it('소개문도 보이는 이미지도 없으면 내용이 없다', () => {
    expect(introductionHasContent(null, new Set())).toBe(false);
    expect(introductionHasContent(intro(), new Set())).toBe(true);
    expect(introductionHasContent(intro(), new Set([IMAGE]))).toBe(false);
    expect(introductionHasContent(intro({ overview: '소개' }), new Set([IMAGE]))).toBe(true);
  });

  it('길거나 줄이 많은 소개문만 접는다', () => {
    expect(introductionNeedsCollapse('짧다')).toBe(false);
    expect(introductionNeedsCollapse('가'.repeat(141))).toBe(true);
    expect(introductionNeedsCollapse('1\n2\n3\n4\n5')).toBe(true);
  });
});
