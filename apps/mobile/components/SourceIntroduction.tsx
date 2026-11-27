import { useState } from 'react';
import { Image, Linking, Pressable, ScrollView, Text, View } from 'react-native';
import {
  introductionNeedsCollapse,
  isIntroductionImageUrl,
  isKoglLicenseUrl,
  sourceAttributionLine,
  visibleIntroductionImages,
} from '@pinvi/domain';
import type {
  IntroductionProvider,
  SourceImage,
  SourceIntroduction as SourceIntroductionData,
} from '@pinvi/schemas';

/**
 * 원본 이미지 1장 + 그 이미지의 공공누리 표시 — 원본 URL 그대로 보이고 누르면 원본을 연다. 변경금지(제3·4유형)를
 * 지키려고 모든 이미지를 크롭·모서리 깎기 없이 원본 비율(`resizeMode="contain"`)로만 그린다.
 */
function OriginalImage({
  provider,
  image,
  width,
  onError,
}: {
  provider: IntroductionProvider;
  image: SourceImage;
  width: number | '100%';
  onError: () => void;
}) {
  return (
    <View style={{ width }} className="gap-0.5" testID="place-sheet-introduction-figure">
      <Pressable
        accessibilityRole="link"
        accessibilityLabel={`${image.alt} — 원본 이미지 열기`}
        accessibilityHint="브라우저에서 열립니다"
        onPress={() => {
          if (isIntroductionImageUrl(provider, image.url)) void Linking.openURL(image.url);
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
      {isKoglLicenseUrl(image.license_url) ? (
        <Pressable
          accessibilityRole="link"
          accessibilityHint="브라우저에서 열립니다"
          onPress={() => void Linking.openURL(image.license_url)}
          className="min-h-11 justify-center"
          testID="place-sheet-introduction-license"
        >
          <Text className="text-xs text-ink underline">{image.license_label}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

/**
 * 출처 장소 소개: 원본 이미지(여러 장이면 가로 갤러리) · 소개문(길면 접기) · 출처(+ 기준일).
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
  return (
    <View className="gap-2" testID="place-sheet-introduction">
      {images.length === 1 ? (
        <OriginalImage
          provider={introduction.provider}
          image={images[0]!}
          width="100%"
          onError={() => onImageError(images[0]!.url)}
        />
      ) : null}
      {images.length > 1 ? (
        <ScrollView
          horizontal
          accessibilityLabel={`사진 ${images.length}장`}
          contentContainerClassName="gap-2"
          testID="place-sheet-introduction-gallery"
        >
          {images.map((image) => (
            <OriginalImage
              key={image.url}
              provider={introduction.provider}
              image={image}
              width={260}
              onError={() => onImageError(image.url)}
            />
          ))}
        </ScrollView>
      ) : null}
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
      <Text className="text-xs text-muted" testID="place-sheet-introduction-attribution">
        {sourceAttributionLine(introduction)}
      </Text>
    </View>
  );
}
