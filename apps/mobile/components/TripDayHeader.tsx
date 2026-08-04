import { Text, View } from 'react-native';
import type { TripViewDay } from '@pinvi/schemas';
import { formatKstTime, formatTripDate, paletteHex, resolveDayMarkerColor } from '@pinvi/domain';

export type TripDayHeaderDay = Pick<
  TripViewDay,
  | 'day_index'
  | 'title'
  | 'date'
  | 'effective_date'
  | 'out_of_range'
  | 'marker_color'
  | 'holidays'
  | 'rise_set'
  | 'rise_set_reference'
>;

/**
 * 일자 요약 헤더 — 웹 `TripDayHeader`(ADR-055 §6, F8) 모바일 대응.
 * effective date + 일자 색 + 공휴일 + 기간 벗어남 + 일출/일몰(순수 표현).
 */
export function TripDayHeader({ day }: { day: TripDayHeaderDay }) {
  const dateLabel = formatTripDate(day.effective_date ?? day.date);
  // marker_color는 override 전용(null=기본) — 인덱스 기본 팔레트 색으로 해석(ADR-055 §3).
  const dayColor = paletteHex(resolveDayMarkerColor(day.day_index, day.marker_color));
  const holidayNames = Array.from(new Set(day.holidays.map((h) => h.name).filter(Boolean)));

  return (
    <View className="gap-1.5">
      <View className="flex-row flex-wrap items-center gap-2">
        <View className="h-3 w-3 rounded-full" style={{ backgroundColor: dayColor }} />
        <Text className="text-base font-semibold text-ink">
          Day {day.day_index}
          {day.title ? ` · ${day.title}` : ''}
        </Text>
        <Text className="text-sm text-muted">{dateLabel}</Text>
        {day.out_of_range ? (
          <View className="self-start rounded-sm bg-error-bg px-1.5 py-0.5">
            <Text className="text-[11px] font-semibold text-error-text">기간 벗어남</Text>
          </View>
        ) : null}
        {holidayNames.map((name) => (
          <View key={name} className="self-start rounded-sm bg-error-bg px-1.5 py-0.5">
            <Text className="text-[11px] font-semibold text-error-text">{name}</Text>
          </View>
        ))}
      </View>
      <TripDayRiseSet day={day} />
    </View>
  );
}

function TripDayRiseSet({ day }: { day: TripDayHeaderDay }) {
  const rs = day.rise_set;
  const sunrise = formatKstTime(rs?.sunrise_at);
  const sunset = formatKstTime(rs?.sunset_at);

  // 성공 + 시각이 있으면 일출/일몰, 아니면 준비 중 안내(좌표/날짜 미확정 등).
  if (rs?.status === 'success' && (sunrise || sunset)) {
    return (
      <View className="flex-row flex-wrap items-center gap-x-3 gap-y-0.5">
        {sunrise ? <Text className="text-xs text-muted">일출 {sunrise}</Text> : null}
        {sunset ? <Text className="text-xs text-muted">일몰 {sunset}</Text> : null}
        {day.rise_set_reference ? (
          <Text className="text-xs text-muted">{day.rise_set_reference} 기준</Text>
        ) : null}
      </View>
    );
  }
  // 준비 중(pending_*)일 때만 안내. failed / success-무값 / null은 표시하지 않는다.
  if (rs != null && rs.status.startsWith('pending')) {
    return <Text className="text-xs text-muted">일출·일몰 준비 중</Text>;
  }
  return null;
}
