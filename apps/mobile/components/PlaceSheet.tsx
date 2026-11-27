import { useMemo, useState, type ReactNode } from 'react';
import { Linking, Modal, Pressable, ScrollView, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useMinuteNow } from '@pinvi/hooks';
import {
  activeAlerts,
  introductionHasContent,
  buildMapLinks,
  featureResolutionNotice,
  hasAnyPlaceDetail,
  placeDetailsRefreshErrorMessage,
  placeDetailsSourceLine,
  telHref,
  todayHoursLine,
  type MapLink,
} from '@pinvi/domain';
import type { FeatureWeatherCard, PoiPlaceDetails, TripViewPoi } from '@pinvi/schemas';
import { useFeatureIntroduction } from '../lib/featureIntroduction';
import { MAP_APP_NAME, openMapLink } from '../lib/mapApps';
import { useKakaoPhone, usePlaceDetails } from '../lib/placeDetails';
import { usePoiWeather } from '../lib/poiWeather';
import { WeatherBadge } from './PoiWeatherBadge';
import { SourceIntroduction } from './SourceIntroduction';
import { Button, Muted } from './ui';

type SectionKey = 'about' | 'hours' | 'memo' | 'links' | 'maps';

export interface PlaceSheetProps {
  tripId: string;
  poi: TripViewPoi;
  coord: { lon: number; lat: number } | null;
  /** 편집할 수 있는 사람이면 장소 편집 화면(`poi/[poiId]`)으로 가는 버튼을 보인다. */
  canEdit: boolean;
  onClose: () => void;
}

/**
 * 읽기 전용 장소 정보 아래 시트 — 웹 `PlaceInfoPanel`(#754) 모바일 대응.
 *
 * 요약(이름·현재 날씨 배지·오늘 영업시간·연결 안내·기상 특보)은 늘 보이고, 영업 정보(저장된 정보 + 저장된 전화가
 * 없을 때 카카오 전화 #758)·메모·링크·지도 앱 열기는 접힌 항목 버튼으로 둔다(한 번에 하나만 펼친다). 편집은
 * 기존 장소 편집 화면에서 한다.
 */
export function PlaceSheet({ tripId, poi, coord, canEdit, onClose }: PlaceSheetProps) {
  const router = useRouter();
  const name = poi.title ?? '장소';
  const [openSection, setOpenSection] = useState<SectionKey | null>(null);
  // 좌표를 모르는 장소는 날씨를 묻지 않는다(목록 배지와 같은 공유 캐시).
  const weather = usePoiWeather(tripId, coord ? poi.poi_id : null);
  const card = 'card' in weather ? weather.card : null;
  const { query, refresh } = usePlaceDetails(tripId, poi.poi_id);
  const details = query.data ?? null;
  const mapLinks = useMemo(
    () => (coord ? buildMapLinks({ name, ...coord }, { appName: MAP_APP_NAME }) : []),
    [coord, name],
  );
  // 출처 소개(TourAPI)는 보여 줄 값이 있을 때만 항목으로 둔다(빈 항목 없음). 응답이 늦게 와도 앞 항목
  // 버튼이 밀리지 않게 고정 항목 뒤(지도 앱 앞)에 붙는다. 깨진 이미지는 시트가 기억해 항목 존재와 내용이
  // 같은 기준(`introductionHasContent`)을 쓴다 — 내용이 사라지면 항목과 펼침도 사라진다.
  const introduction = useFeatureIntroduction(poi.feature_id);
  const [failedImageUrls, setFailedImageUrls] = useState<ReadonlySet<string>>(() => new Set());
  const about = introductionHasContent(introduction, failedImageUrls) ? (
    <SourceIntroduction
      introduction={introduction}
      failedImageUrls={failedImageUrls}
      onImageError={(url) => setFailedImageUrls((prev) => new Set(prev).add(url))}
    />
  ) : null;
  const sectionKeys: SectionKey[] = [
    'hours',
    'memo',
    'links',
    ...(about ? ['about' as const] : []),
    ...(mapLinks.length ? ['maps' as const] : []),
  ];
  const shownSection = openSection && sectionKeys.includes(openSection) ? openSection : null;
  const openEditor = () => {
    onClose();
    router.push(`/trips/${tripId}/poi/${poi.poi_id}`);
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <View className="flex-1 justify-end">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="장소 정보 닫기"
          onPress={onClose}
          className="absolute inset-0 bg-scrim/30"
        />
        <View
          className="max-h-[75%] rounded-t-lg border border-hairline bg-canvas px-4 pb-6 pt-3"
          accessibilityLabel={`${name} 장소 정보`}
          testID="place-sheet"
        >
          <SheetSummary name={name} poi={poi} card={card} details={details} onClose={onClose} />
          <SectionToggles keys={sectionKeys} open={shownSection} onToggle={setOpenSection} />
          {shownSection ? (
            <ScrollView className="mt-2" testID={`place-sheet-${shownSection}`}>
              <SectionContent
                section={shownSection}
                tripId={tripId}
                poi={poi}
                details={details}
                detailsLoading={query.isLoading}
                refresh={refresh}
                mapLinks={mapLinks}
                about={about}
              />
            </ScrollView>
          ) : null}
          {canEdit ? (
            <Button label="장소 편집" variant="secondary" className="mt-3" onPress={openEditor} />
          ) : null}
        </View>
      </View>
    </Modal>
  );
}

const SECTION_TITLES: Record<SectionKey, string> = {
  about: '소개',
  hours: '영업 정보',
  memo: '메모',
  links: '링크',
  maps: '지도 앱',
};

/** 늘 보이는 요약 — 이름·현재 날씨 배지·오늘 영업시간·연결 안내·기상 특보. */
function SheetSummary({
  name,
  poi,
  card,
  details,
  onClose,
}: {
  name: string;
  poi: TripViewPoi;
  card: FeatureWeatherCard | null;
  details: PoiPlaceDetails | null;
  onClose: () => void;
}) {
  const now = useMinuteNow();
  const alerts = useMemo(() => (now ? activeAlerts(card, now) : []), [card, now]);
  const todayHours = details && now ? todayHoursLine(details.opening_hours, now) : null;
  const resolutionNotice = featureResolutionNotice(poi.feature_resolution_state);
  return (
    <View className="flex-row items-start gap-2">
      <View className="flex-1 gap-1">
        <Text className="text-base font-bold text-ink" testID="place-sheet-title">
          {name}
        </Text>
        <View className="flex-row flex-wrap items-center gap-x-3 gap-y-1">
          <WeatherBadge card={card} />
          {todayHours ? (
            <Text className="text-xs text-body" testID="place-sheet-today-hours">
              {todayHours}
            </Text>
          ) : null}
        </View>
        {resolutionNotice ? (
          <Text className="text-xs text-error-text">{resolutionNotice}</Text>
        ) : null}
        {alerts.length > 0 ? (
          <Text className="text-xs font-semibold text-error-text" testID="place-sheet-alert">
            {alerts.map((alert) => alert.title).join(', ')}
          </Text>
        ) : null}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="닫기"
        onPress={onClose}
        className="min-h-11 min-w-11 items-center justify-center"
      >
        <Text className="text-sm text-muted">닫기</Text>
      </Pressable>
    </View>
  );
}

/** 접힌 항목 버튼 한 줄 — 한 번에 하나만 펼친다. */
function SectionToggles({
  keys,
  open,
  onToggle,
}: {
  keys: SectionKey[];
  open: SectionKey | null;
  onToggle: (next: SectionKey | null) => void;
}) {
  return (
    <View className="mt-2 flex-row flex-wrap gap-1 border-t border-hairline pt-2">
      {keys.map((key) => {
        const expanded = key === open;
        return (
          <Pressable
            key={key}
            accessibilityRole="button"
            accessibilityState={{ expanded }}
            onPress={() => onToggle(expanded ? null : key)}
            testID={`place-sheet-${key}-toggle`}
            className={`min-h-11 justify-center rounded-sm px-3 ${expanded ? 'bg-ink' : 'bg-surface-soft'}`}
          >
            <Text className={`text-xs font-semibold ${expanded ? 'text-canvas' : 'text-ink'}`}>
              {SECTION_TITLES[key]}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

function SectionContent({
  section,
  tripId,
  poi,
  details,
  detailsLoading,
  refresh,
  mapLinks,
  about,
}: {
  section: SectionKey;
  tripId: string;
  poi: TripViewPoi;
  details: PoiPlaceDetails | null;
  detailsLoading: boolean;
  refresh: ReturnType<typeof usePlaceDetails>['refresh'];
  mapLinks: MapLink[];
  about: ReactNode;
}) {
  switch (section) {
    case 'about':
      return about;
    case 'hours':
      return (
        <HoursContent
          tripId={tripId}
          poiId={poi.poi_id}
          loading={detailsLoading}
          details={details}
          refreshing={refresh.isPending}
          refreshError={refresh.isError ? placeDetailsRefreshErrorMessage(refresh.error) : null}
          refreshed={refresh.isSuccess}
          onRefresh={() => refresh.mutate()}
        />
      );
    case 'memo':
      return poi.user_note ? (
        <Text className="text-sm text-body">{poi.user_note}</Text>
      ) : (
        <Muted>메모가 없습니다.</Muted>
      );
    case 'links':
      return <LinksContent userUrl={poi.user_url} website={details?.website ?? null} />;
    case 'maps':
      return (
        <View className="flex-row gap-2">
          {mapLinks.map((link) => (
            <MapLinkButton key={link.provider} link={link} />
          ))}
        </View>
      );
  }
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View className="gap-0.5">
      <Text className="text-xs font-semibold text-muted">{label}</Text>
      {children}
    </View>
  );
}

function LinkText({ url, label, testID }: { url: string; label?: string; testID?: string }) {
  return (
    <Text
      accessibilityRole="link"
      onPress={() => void Linking.openURL(url)}
      className="text-sm text-primary"
      testID={testID}
    >
      {label ?? url}
    </Text>
  );
}

function DetailsList({ details }: { details: PoiPlaceDetails }) {
  return (
    <View className="gap-2" testID="place-sheet-hours-body">
      {details.opening_hours.length > 0 ? (
        <DetailRow label="영업시간">
          {details.opening_hours.map((line) => (
            <Text key={line} className="text-sm text-body">
              {line}
            </Text>
          ))}
        </DetailRow>
      ) : null}
      {details.closed_days ? (
        <DetailRow label="휴무일">
          <Text className="text-sm text-body">{details.closed_days}</Text>
        </DetailRow>
      ) : null}
      {details.phone ? (
        <DetailRow label="전화">
          <LinkText url={telHref(details.phone)} label={details.phone} testID="place-sheet-phone" />
        </DetailRow>
      ) : null}
      {details.website ? (
        <DetailRow label="웹사이트">
          <LinkText url={details.website} />
        </DetailRow>
      ) : null}
    </View>
  );
}

/** 저장된 전화가 없을 때 카카오에서 표시 시점에 찾은 전화(저장하지 않음) + 출처 링크. */
function KakaoPhone({ tripId, poiId }: { tripId: string; poiId: string }) {
  const match = useKakaoPhone(tripId, poiId, true).data;
  if (!match?.phone) return null;
  return (
    <View className="mt-2 gap-0.5" testID="place-sheet-kakao-phone">
      <Text className="text-xs font-semibold text-muted">전화 (카카오)</Text>
      <View className="flex-row flex-wrap items-center gap-x-2">
        <LinkText url={telHref(match.phone)} label={match.phone} />
        {match.provider_url ? <LinkText url={match.provider_url} label="출처: 카카오맵" /> : null}
      </View>
    </View>
  );
}

function HoursContent({
  tripId,
  poiId,
  loading,
  details,
  refreshing,
  refreshError,
  refreshed,
  onRefresh,
}: {
  tripId: string;
  poiId: string;
  loading: boolean;
  details: PoiPlaceDetails | null;
  refreshing: boolean;
  refreshError: string | null;
  refreshed: boolean;
  onRefresh: () => void;
}) {
  // 저장된 전화(공공데이터)가 있으면 카카오를 부르지 않는다.
  const needsKakaoPhone = !loading && !details?.phone;
  let body: ReactNode;
  if (loading && !details) body = <Muted>불러오는 중</Muted>;
  else if (hasAnyPlaceDetail(details)) body = <DetailsList details={details} />;
  else body = <Muted>확인된 영업 정보가 없습니다.</Muted>;
  return (
    <View className="gap-2">
      {body}
      {needsKakaoPhone ? <KakaoPhone tripId={tripId} poiId={poiId} /> : null}
      <View className="flex-row items-center gap-2">
        <Muted className="flex-1">{placeDetailsSourceLine(details)}</Muted>
        <Button
          label="다시 읽어오기"
          variant="secondary"
          loading={refreshing}
          disabled={loading}
          onPress={onRefresh}
        />
      </View>
      {refreshError ? <Text className="text-xs text-error-text">{refreshError}</Text> : null}
      {refreshed ? (
        <Text className="text-xs text-success-text">장소 정보를 다시 읽어왔습니다.</Text>
      ) : null}
    </View>
  );
}

function LinksContent({ userUrl, website }: { userUrl: string | null; website: string | null }) {
  const links = [userUrl, website && website !== userUrl ? website : null].filter(
    (value): value is string => Boolean(value),
  );
  if (links.length === 0) return <Muted>링크가 없습니다.</Muted>;
  return (
    <View className="gap-1">
      {links.map((url) => (
        <LinkText key={url} url={url} />
      ))}
    </View>
  );
}

function MapLinkButton({ link }: { link: MapLink }) {
  return (
    <Pressable
      accessibilityRole="link"
      onPress={() => void openMapLink(link)}
      testID={`place-sheet-map-${link.provider}`}
      className="min-h-11 flex-1 items-center justify-center rounded-sm border border-hairline px-2"
    >
      <Text className="text-sm font-semibold text-ink">{link.label}</Text>
    </Pressable>
  );
}
