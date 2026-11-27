import { useCallback, useState } from 'react';
import {
  FlatList,
  Image,
  Linking,
  Pressable,
  Text,
  View,
  type ListRenderItemInfo,
} from 'react-native';
import {
  introductionNeedsCollapse,
  isIntroductionImageUrl,
  isKoglLicenseUrl,
  sourceAttributionLine,
  visibleIntroductionImages,
} from '@pinvi/domain';
import type { SourceImage, SourceIntroduction as SourceIntroductionData } from '@pinvi/schemas';

const NO_FAILED: ReadonlySet<string> = new Set();
const GALLERY_ITEM_WIDTH = 260;

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
  provider: string;
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

function GallerySeparator() {
  return <View style={{ width: 8 }} />;
}

const GALLERY_ITEM_STRIDE = GALLERY_ITEM_WIDTH + 8;

function galleryItemLayout(_data: ArrayLike<SourceImage> | null | undefined, index: number) {
  return { length: GALLERY_ITEM_STRIDE, offset: GALLERY_ITEM_STRIDE * index, index };
}

function imageKey(image: SourceImage): string {
  return image.url;
}

/** 여러 장 — 화면 가까이 있는 사진만 그린다(가상화). 보이지 않는 사진까지 미리 받지 않는다. */
function Gallery({
  provider,
  images,
  onImageError,
}: {
  provider: string;
  images: SourceImage[];
  onImageError: (url: string) => void;
}) {
  const renderItem = useCallback(
    ({ item }: ListRenderItemInfo<SourceImage>) => (
      <OriginalImage
        provider={provider}
        image={item}
        width={GALLERY_ITEM_WIDTH}
        onError={() => onImageError(item.url)}
      />
    ),
    [provider, onImageError],
  );
  return (
    <FlatList
      horizontal
      data={images}
      keyExtractor={imageKey}
      initialNumToRender={2}
      maxToRenderPerBatch={2}
      windowSize={3}
      getItemLayout={galleryItemLayout}
      ItemSeparatorComponent={GallerySeparator}
      accessibilityLabel={`사진 ${images.length}장`}
      testID="place-sheet-introduction-gallery"
      renderItem={renderItem}
    />
  );
}

/** 소개문 — 텍스트로만 그리고, 길면 접어 두고 "더 보기"로 펼친다. */
function Overview({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  const collapsible = introductionNeedsCollapse(text);
  return (
    <View>
      <Text
        className="text-sm text-body"
        numberOfLines={collapsible && !expanded ? 4 : undefined}
        testID="place-sheet-introduction-overview"
      >
        {text}
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
  const { overview, provider } = introduction;
  const images = visibleIntroductionImages(introduction, failedImageUrls);
  if (!overview && images.length === 0) return null;
  // 레이아웃은 처음 받은(허용된) 장수로 정한다 — 갤러리에서 한 장이 깨져 1장이 남아도 틀이 바뀌지 않게.
  const gallery = visibleIntroductionImages(introduction, NO_FAILED).length > 1;
  const single = !gallery ? images[0] : undefined;
  return (
    <View className="gap-2" testID="place-sheet-introduction">
      {single ? (
        <OriginalImage
          provider={provider}
          image={single}
          width="100%"
          onError={() => onImageError(single.url)}
        />
      ) : null}
      {gallery && images.length > 0 ? (
        <Gallery provider={provider} images={images} onImageError={onImageError} />
      ) : null}
      {overview ? <Overview text={overview} /> : null}
      <Text className="text-xs text-muted" testID="place-sheet-introduction-attribution">
        {sourceAttributionLine(introduction)}
      </Text>
    </View>
  );
}
