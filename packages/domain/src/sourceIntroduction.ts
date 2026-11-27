/**
 * 장소 출처 소개(TourAPI — 한국관광공사) 공용 판정. 웹 `SourceIntroduction`·모바일 `SourceIntroduction`과
 * 그것을 항목으로 두는 웹 `PlaceInfoPanel`·모바일 `PlaceSheet`이 같은 기준으로 "보여 줄 것이 있는지"를 정한다.
 */
import type { SourceImage, SourceIntroduction } from '@pinvi/schemas';

/** 이 길이 또는 줄 수를 넘는 소개문만 접어 두고 "더 보기"를 단다. */
const COLLAPSE_MIN_CHARS = 140;
const COLLAPSE_MIN_LINES = 4;

const IMAGE_HOST_SUFFIX = '.visitkorea.or.kr';
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

/** 이미지 원본 URL이 TourAPI 이미지 호스트의 https인지(서버도 같은 규칙으로 거른다 — 이중 확인). */
export function isTourapiImageUrl(url: string): boolean {
  return isHttpsOn(url, (u) => u.hostname.endsWith(IMAGE_HOST_SUFFIX));
}

/** 공공누리 유형 설명 링크가 kogl.or.kr https인지. */
export function isKoglLicenseUrl(url: string | null): url is string {
  return url !== null && url.startsWith(KOGL_LICENSE_PREFIX) && isHttpsOn(url, () => true);
}

/** 지금 보여 줄 이미지 — 허용 호스트이고 불러오기에 실패하지 않은 것. */
export function visibleIntroductionImages(
  introduction: SourceIntroduction,
  failedUrls: ReadonlySet<string>,
): SourceImage[] {
  return introduction.images.filter(
    (image) => isTourapiImageUrl(image.url) && !failedUrls.has(image.url),
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
