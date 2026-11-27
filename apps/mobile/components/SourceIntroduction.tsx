import { useState } from 'react';
import { Image, Linking, Pressable, Text, View } from 'react-native';
import {
  introductionNeedsCollapse,
  isKoglLicenseUrl,
  isTourapiImageUrl,
  visibleIntroductionImages,
} from '@pinvi/domain';
import type { SourceImage, SourceIntroduction as SourceIntroductionData } from '@pinvi/schemas';

/**
 * 원본 이미지 1장 — 원본 URL 그대로 보이고 누르면 원본을 연다. 공공누리 제3유형(변경금지)을 지키려고 모든
 * 이미지를 크롭·모서리 깎기 없이 원본 비율(`resizeMode="contain"`)로만 그린다.
 */
function OriginalImage({ image, onError }: { image: SourceImage; onError: () => void }) {
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={`${image.alt} — 원본 이미지 열기`}
      accessibilityHint="브라우저에서 열립니다"
      onPress={() => {
        if (isTourapiImageUrl(image.url)) void Linking.openURL(image.url);
      }}
      className="border border-hairline bg-surface-soft p-1"
      testID="place-sheet-introduction-image-link"
    >
      <Image
        source={{ uri: image.url }}
        accessibilityIgnoresInvertColors
        accessible={false}
        resizeMode="contain"
        onError={onError}
        style={{ width: '100%', height: 180 }}
        testID="place-sheet-introduction-image"
      />
    </Pressable>
  );
}

/**
 * 출처 장소 소개(TourAPI — 한국관광공사): 대표 이미지 · 소개문(길면 접기) · 출처/공공누리 표시.
 * 깨진 이미지 기록은 시트가 가진다(항목 존재와 내용을 같은 기준으로 판정 — `introductionHasContent`).
 */
export function SourceIntroduction({
  introduction,
  failedImageUrls,
  onImageError,
}: {
  introduction: SourceIntroductionData;
  failedImageUrls: ReadonlySet<string>;
  onImageError: (url: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const { overview } = introduction;
  const images = visibleIntroductionImages(introduction, failedImageUrls);
  if (!overview && images.length === 0) return null;
  const collapsible = overview ? introductionNeedsCollapse(overview) : false;
  const licenseUrl = introduction.license_url;
  return (
    <View className="gap-2" testID="place-sheet-introduction">
      {images.map((image) => (
        <OriginalImage key={image.url} image={image} onError={() => onImageError(image.url)} />
      ))}
      {overview ? (
        <View>
          <Text
            className="text-sm text-body"
            numberOfLines={collapsible && !expanded ? 4 : undefined}
            testID="place-sheet-introduction-overview"
          >
            {overview}
          </Text>
          {collapsible ? (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded }}
              onPress={() => setExpanded((value) => !value)}
              className="min-h-11 justify-center"
              testID="place-sheet-introduction-overview-toggle"
            >
              <Text className="text-xs font-semibold text-ink underline">
                {expanded ? '소개 접기' : '소개 더 보기'}
              </Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      <View className="gap-0.5" testID="place-sheet-introduction-attribution">
        <Text className="text-xs text-muted">출처: {introduction.attribution}</Text>
        {images.length > 0 && introduction.license_label && isKoglLicenseUrl(licenseUrl) ? (
          <Pressable
            accessibilityRole="link"
            accessibilityHint="브라우저에서 열립니다"
            onPress={() => void Linking.openURL(licenseUrl)}
            className="min-h-11 justify-center"
            testID="place-sheet-introduction-license"
          >
            <Text className="text-xs text-ink underline">{introduction.license_label}</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}
