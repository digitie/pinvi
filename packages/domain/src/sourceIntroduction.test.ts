import { describe, expect, it } from 'vitest';
import type { FeatureDetailCard, SourceImage, SourceIntroduction } from '@pinvi/schemas';
import {
  cardIntroduction,
  introductionHasContent,
  introductionNeedsCollapse,
  isIntroductionImageUrl,
  isKoglLicenseUrl,
  isTourapiImageUrl,
  sourceAttributionLine,
  visibleIntroductionImages,
} from './sourceIntroduction';

const IMAGE = 'https://tong.visitkorea.or.kr/cms/resource/a.jpg';

function image(over: Partial<SourceImage> = {}): SourceImage {
  return {
    url: IMAGE,
    alt: 'a',
    kogl_type: 3,
    no_derivatives: true,
    license_label: '공공누리 제3유형: 출처표시 + 변경금지',
    license_url: 'https://www.kogl.or.kr/info/licenseType3.do',
    ...over,
  };
}

function intro(over: Partial<SourceIntroduction> = {}): SourceIntroduction {
  return {
    provider: 'tourapi',
    attribution: '한국관광공사',
    reference_date: null,
    overview: null,
    images: [image()],
    kogl_type: null,
    license_label: null,
    license_url: null,
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

  it('이미지 허용 호스트가 없는 원천(국가유산 등)은 이미지를 받지 않는다', () => {
    expect(isIntroductionImageUrl('krheritage', 'https://www.khs.go.kr/a.jpg')).toBe(false);
    expect(isIntroductionImageUrl('krheritage', IMAGE)).toBe(false);
    const heritage = intro({ provider: 'krheritage', overview: '설명' });
    expect(visibleIntroductionImages(heritage, new Set())).toEqual([]);
  });

  it('공공누리 링크는 kogl.or.kr https만 받는다', () => {
    expect(isKoglLicenseUrl('https://www.kogl.or.kr/info/licenseType1.do')).toBe(true);
    expect(isKoglLicenseUrl('https://www.kogl.or.kr.evil.example/')).toBe(false);
    expect(isKoglLicenseUrl('intent://x')).toBe(false);
    expect(isKoglLicenseUrl(null)).toBe(false);
  });

  it('깨진 이미지·허용 밖 이미지·공공누리 링크가 이상한 이미지는 보이는 이미지에서 빠진다', () => {
    const data = intro({
      images: [
        image(),
        image({ url: 'https://evil.example/b.jpg' }),
        image({ url: 'https://tong.visitkorea.or.kr/c.jpg', license_url: 'https://evil.example' }),
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

  it('출처 줄은 기준일이 있으면 함께 적는다', () => {
    expect(sourceAttributionLine({ attribution: '한국관광공사', reference_date: null })).toBe(
      '출처: 한국관광공사',
    );
    expect(sourceAttributionLine({ attribution: 'X', reference_date: '2026-05-31' })).toBe(
      '출처: X · 기준일 2026-05-31',
    );
  });

  it('place·event 카드만 출처 소개를 준다', () => {
    const base = {
      feature_id: 'f',
      name: 'n',
      coord: null,
      category: null,
      category_label: null,
      address_line: null,
      marker_color: 'P-13',
      marker_icon: 'marker',
      homepage_url: null,
      enrichment: [],
      degraded_providers: [],
      containing_areas: [],
    };
    const event = {
      ...base,
      kind: 'event',
      start_date: null,
      end_date: null,
      venue: null,
      introduction: intro({ overview: '축제' }),
      visit_guide: null,
    } satisfies FeatureDetailCard;
    expect(cardIntroduction(event)?.overview).toBe('축제');
    expect(
      cardIntroduction({ ...base, kind: 'notice', body: null, start_date: null, end_date: null }),
    ).toBeNull();
    expect(cardIntroduction(null)).toBeNull();
    // 모르는 원천은 보이지 않는다(출처 표시 조건을 모른다).
    expect(
      cardIntroduction({ ...event, introduction: intro({ provider: 'new_source' }) }),
    ).toBeNull();
  });
});
