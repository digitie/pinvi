/**
 * 장소 출처 소개(소개문·원본 이미지 갤러리·출처/공공누리) 공용 판정. 웹 `SourceIntroduction`·모바일
 * `SourceIntroduction`과 그것을 항목으로 두는 웹 `PlaceInfoPanel`·모바일 `PlaceSheet`이 같은 기준으로
 * "보여 줄 것이 있는지"를 정한다.
 */
import type {
  FeatureDetailCard,
  IntroductionProvider,
  SourceImage,
  SourceIntroduction,
  VisitGuide,
} from '@pinvi/schemas';

/** 이 길이 또는 줄 수를 넘는 소개문만 접어 두고 "더 보기"를 단다. */
const COLLAPSE_MIN_CHARS = 140;
const COLLAPSE_MIN_LINES = 4;

/** 원천별 이미지 허용 호스트(서버 `_IMAGE_HOST_SUFFIX`와 같다). 없는 원천은 이미지를 받지 않는다. */
const IMAGE_HOST_SUFFIX: Partial<Record<IntroductionProvider, string>> = {
  tourapi: '.visitkorea.or.kr',
};

/** 화면이 아는 원천 — 이 밖의 원천은 출처 표시 조건을 모르므로 블록을 보이지 않는다. */
const KNOWN_PROVIDERS: readonly string[] = [
  'tourapi',
  'krheritage',
  'datagokr_museum',
  'krforest_recreation_forest',
] satisfies IntroductionProvider[];

export function isKnownIntroductionProvider(provider: string): provider is IntroductionProvider {
  return KNOWN_PROVIDERS.includes(provider);
}
const KOGL_LICENSE_PREFIX = 'https://www.kogl.or.kr/';

export function introductionNeedsCollapse(text: string): boolean {
  return text.length > COLLAPSE_MIN_CHARS || text.split('\n').length > COLLAPSE_MIN_LINES;
}

function isHttpsOn(url: string, check: (u: URL) => boolean): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' && !parsed.username && !parsed.password && check(parsed);
  } catch {
    return false;
  }
}

/** 이미지 원본 URL이 그 원천의 허용 호스트 https인지(서버도 같은 규칙으로 거른다 — 이중 확인). */
export function isIntroductionImageUrl(provider: string, url: string): boolean {
  const suffix = isKnownIntroductionProvider(provider) ? IMAGE_HOST_SUFFIX[provider] : undefined;
  return suffix !== undefined && isHttpsOn(url, (u) => u.hostname.endsWith(suffix));
}

/** TourAPI 이미지 호스트(`*.visitkorea.or.kr`) https인지. */
export function isTourapiImageUrl(url: string): boolean {
  return isIntroductionImageUrl('tourapi', url);
}

/** 공공누리 유형 설명 링크가 kogl.or.kr https인지. */
export function isKoglLicenseUrl(url: string | null | undefined): url is string {
  return url != null && url.startsWith(KOGL_LICENSE_PREFIX) && isHttpsOn(url, () => true);
}

/** 지금 보여 줄 이미지 — 허용 호스트이고 공공누리 링크가 맞고 불러오기에 실패하지 않은 것. */
export function visibleIntroductionImages(
  introduction: SourceIntroduction,
  failedUrls: ReadonlySet<string>,
): SourceImage[] {
  return introduction.images.filter(
    (image) =>
      isIntroductionImageUrl(introduction.provider, image.url) &&
      isKoglLicenseUrl(image.license_url) &&
      !failedUrls.has(image.url),
  );
}

/** 소개문 또는 보이는 이미지가 하나라도 있으면 true — 없으면 블록·항목을 만들지 않는다. */
export function introductionHasContent(
  introduction: SourceIntroduction | null | undefined,
  failedUrls: ReadonlySet<string>,
): introduction is SourceIntroduction {
  if (!introduction) return false;
  return (
    Boolean(introduction.overview) || visibleIntroductionImages(introduction, failedUrls).length > 0
  );
}

/** 상세 카드의 출처 소개 — place·event(TourAPI 축제)만 가진다. 모르는 원천이면 null. */
export function cardIntroduction(
  card: FeatureDetailCard | null | undefined,
): SourceIntroduction | null {
  const introduction =
    card && (card.kind === 'place' || card.kind === 'event') ? card.introduction : null;
  return introduction && isKnownIntroductionProvider(introduction.provider) ? introduction : null;
}

/** 상세 카드의 이용 안내 — place·event만 가진다. 모르는 원천이면 null. */
export function cardVisitGuide(card: FeatureDetailCard | null | undefined): VisitGuide | null {
  const guide = card && (card.kind === 'place' || card.kind === 'event') ? card.visit_guide : null;
  return guide && isKnownIntroductionProvider(guide.provider) ? guide : null;
}

/** 출처 줄 — "출처: 한국관광공사" 또는 "출처: … · 기준일 2026-05-31". */
export function sourceAttributionLine(source: {
  attribution: string;
  reference_date: string | null;
}): string {
  return source.reference_date
    ? `출처: ${source.attribution} · 기준일 ${source.reference_date}`
    : `출처: ${source.attribution}`;
}
