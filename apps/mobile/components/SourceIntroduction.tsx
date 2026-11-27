import { useState } from 'react';
import { Image, Linking, Pressable, Text, View } from 'react-native';
import type { SourceImage, SourceIntroduction as SourceIntroductionData } from '@pinvi/schemas';

/** 이 길이 또는 줄 수를 넘는 소개문만 접어 두고 "더 보기"를 단다(웹과 같다). */
const COLLAPSE_MIN_CHARS = 140;
const COLLAPSE_MIN_LINES = 4;

function needsCollapse(text: string): boolean {
  return text.length > COLLAPSE_MIN_CHARS || text.split('\n').length > COLLAPSE_MIN_LINES;
}

/**
 * 원본 이미지 1장 — 원본 URL 그대로 보이고 누르면 원본을 연다. 공공누리 제3유형(변경금지)을 지키려고 모든
 * 이미지를 크롭 없이 원본 비율(`resizeMode="contain"`)로만 그린다.
 */
function OriginalImage({ image, onError }: { image: SourceImage; onError: () => void }) {
  return (
    <Pressable
      accessibilityRole="link"
      accessibilityLabel={`${image.alt} — 원본 이미지 열기`}
      onPress={() => void Linking.openURL(image.url)}
      className="overflow-hidden rounded-sm border border-hairline bg-surface-soft"
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

/** 출처 장소 소개(TourAPI — 한국관광공사): 대표 이미지 · 소개문(길면 접기) · 출처/공공누리 표시. */
export function SourceIntroduction({ introduction }: { introduction: SourceIntroductionData }) {
  const [expanded, setExpanded] = useState(false);
  const [failedUrls, setFailedUrls] = useState<ReadonlySet<string>>(() => new Set());
  const { overview } = introduction;
  const images = introduction.images.filter((image) => !failedUrls.has(image.url));
  if (!overview && images.length === 0) return null;
  const collapsible = overview ? needsCollapse(overview) : false;
  return (
    <View className="gap-2" testID="place-sheet-introduction">
      {images.map((image) => (
        <OriginalImage
          key={image.url}
          image={image}
          onError={() => setFailedUrls((prev) => new Set(prev).add(image.url))}
        />
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
              <Text className="text-xs font-semibold text-primary">
                {expanded ? '소개 접기' : '소개 더 보기'}
              </Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      <View
        className="flex-row flex-wrap items-center gap-x-1.5"
        testID="place-sheet-introduction-attribution"
      >
        <Text className="text-xs text-muted">출처: {introduction.attribution}</Text>
        {images.length > 0 && introduction.license_label && introduction.license_url ? (
          <Text
            accessibilityRole="link"
            onPress={() => void Linking.openURL(introduction.license_url as string)}
            className="text-xs text-primary"
            testID="place-sheet-introduction-license"
          >
            · {introduction.license_label}
          </Text>
        ) : null}
      </View>
    </View>
  );
}
