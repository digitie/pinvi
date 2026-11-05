import type { TripView } from '@pinvi/schemas';
import { tripDaysToMapPoints, type TripMapPoint } from '@pinvi/domain';

export type TripExportSource = Pick<TripView, 'trip' | 'days'>;
export interface ExportPoi {
  id: string;
  name: string;
  note: string | null;
  arrival: string | null;
  departure: string | null;
  address: string | null;
}
export interface ExportDay {
  index: number;
  date: string | null;
  title: string | null;
  note: string | null;
  pois: ExportPoi[];
}
export interface TripExportModel {
  id: string;
  title: string;
  description: string | null;
  startDate: string | null;
  endDate: string | null;
  days: ExportDay[];
  points: Pick<
    TripMapPoint,
    'poiId' | 'dayIndex' | 'title' | 'lon' | 'lat' | 'color' | 'labelColor'
  >[];
}

function plusDays(date: string, offset: number): string | null {
  const value = new Date(date + 'T00:00:00Z');
  value.setUTCDate(value.getUTCDate() + offset);
  const result = value.toISOString().slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(result) ? result : null;
}

function addressLabel(feature: Record<string, unknown>): string | null {
  if (typeof feature.address_label === 'string') return feature.address_label;
  if (typeof feature.address === 'string') return feature.address;
  if (feature.address && typeof feature.address === 'object') {
    const label = (feature.address as Record<string, unknown>).label;
    if (typeof label === 'string') return label;
  }
  return null;
}

/** 권한별 API가 이미 반환한 화면 데이터에서 내보내기용 필드만 복사한다. */
export function buildTripExport(source: TripExportSource): TripExportModel {
  return {
    id: source.trip.trip_id,
    title: source.trip.title,
    description: source.trip.description,
    startDate: source.trip.start_date,
    endDate: source.trip.end_date,
    days: [...source.days]
      .sort((a, b) => a.day_index - b.day_index)
      .map((day) => ({
        index: day.day_index,
        date:
          day.effective_date ??
          day.date ??
          (source.trip.start_date ? plusDays(source.trip.start_date, day.day_index - 1) : null),
        title: day.title,
        note: day.note,
        pois: [...day.pois]
          .sort((a, b) => (a.sort_order < b.sort_order ? -1 : a.sort_order > b.sort_order ? 1 : 0))
          .map((poi) => ({
            id: poi.poi_id,
            name: poi.title ?? (typeof poi.feature.name === 'string' ? poi.feature.name : '장소'),
            note: poi.user_note,
            arrival: poi.planned_arrival_at,
            departure: poi.planned_departure_at,
            address: addressLabel(poi.feature),
          })),
      })),
    // 새로 지역/좌표를 추측하지 않고 기존 화면의 검증된 포인트 변환을 사용한다.
    points: tripDaysToMapPoints(source.days).map((point) => ({
      poiId: point.poiId,
      dayIndex: point.dayIndex,
      title: point.title,
      lon: point.lon,
      lat: point.lat,
      color: point.color,
      labelColor: point.labelColor,
    })),
  };
}

export function exportFilename(title: string, extension: 'ics'): string {
  const safe = title
    .replace(/[^\p{L}\p{N}._ -]/gu, '_')
    .replace(/^\.+|\.+$/g, '')
    .trim()
    .slice(0, 70);
  return (safe || '여행') + '-일정.' + extension;
}

export function escapeCalendarText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/\r\n|\r|\n/g, '\\n')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g, '');
}

/** continuation의 첫 공백도 75octet 상한에 포함하고 UTF-8 code point를 자르지 않는다. */
export function foldCalendarLine(line: string): string {
  const encoder = new TextEncoder();
  const lines: string[] = [];
  let current = '';
  let bytes = 0;
  for (const character of line) {
    const size = encoder.encode(character).length;
    if (bytes + size > 75) {
      lines.push(current);
      current = ' ';
      bytes = 1;
    }
    current += character;
    bytes += size;
  }
  lines.push(current);
  return lines.join('\r\n');
}

function utcStamp(value: string): string {
  return new Date(value)
    .toISOString()
    .replace(/[-:]/g, '')
    .replace(/\.\d{3}Z$/, 'Z');
}
function knownStamp(value: string | null): value is string {
  return (
    value !== null && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value))
  );
}

export interface CalendarExport {
  content: string;
  events: number;
  omitted: number;
  invalidEnds: number;
}
export function buildTripCalendar(
  model: TripExportModel,
  generatedAt = new Date(),
): CalendarExport {
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Pinvi//Trip Export//KO',
    'CALSCALE:GREGORIAN',
  ];
  let events = 0,
    omitted = 0,
    invalidEnds = 0;
  for (const day of model.days) {
    const entries: (ExportPoi | null)[] = day.pois.length ? day.pois : [null];
    for (const poi of entries) {
      const arrival = poi && knownStamp(poi.arrival) ? poi.arrival : null;
      const departure = poi && knownStamp(poi.departure) ? poi.departure : null;
      const start = arrival ?? departure;
      if (!start && !day.date) {
        omitted += 1;
        continue;
      }
      lines.push('BEGIN:VEVENT');
      lines.push(
        'UID:' + escapeCalendarText(`${model.id}-${poi?.id ?? 'day-' + day.index}@pinvi.example`),
      );
      lines.push('DTSTAMP:' + utcStamp(generatedAt.toISOString()));
      if (start) {
        lines.push('DTSTART:' + utcStamp(start));
        if (arrival && departure) {
          if (Date.parse(departure) > Date.parse(arrival))
            lines.push('DTEND:' + utcStamp(departure));
          else invalidEnds += 1;
        }
      } else {
        lines.push('DTSTART;VALUE=DATE:' + day.date!.replace(/-/g, ''));
        const end = plusDays(day.date!, 1);
        if (end) lines.push('DTEND;VALUE=DATE:' + end.replace(/-/g, ''));
      }
      const title = `${model.title} · ${day.index}일차 · ${poi?.name ?? day.title ?? '일정'}`;
      const description = [
        day.title,
        day.note,
        poi?.note,
        arrival ? '도착: ' + formatExportTime(arrival) : null,
        departure ? '출발: ' + formatExportTime(departure) : null,
        !arrival && departure ? '출발 시각만 확인된 일정입니다.' : null,
      ]
        .filter(Boolean)
        .join('\n');
      lines.push('SUMMARY:' + escapeCalendarText(title));
      if (description) lines.push('DESCRIPTION:' + escapeCalendarText(description));
      if (poi?.address) lines.push('LOCATION:' + escapeCalendarText(poi.address));
      lines.push('END:VEVENT');
      events += 1;
    }
  }
  lines.push('END:VCALENDAR');
  return {
    content: lines.map(foldCalendarLine).join('\r\n') + '\r\n',
    events,
    omitted,
    invalidEnds,
  };
}

export function formatExportTime(value: string | null): string {
  if (!knownStamp(value)) return '미정';
  return (
    new Intl.DateTimeFormat('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    }).format(new Date(value)) + ' KST'
  );
}
