import { describe, expect, it } from 'vitest';
import {
  buildTripCalendar,
  buildTripExport,
  escapeCalendarText,
  exportFilename,
  foldCalendarLine,
  formatExportTime,
} from '../lib/tripExport';
import { exportSource } from './fixtures/tripExport';

const generated = new Date('2026-11-01T00:00:00Z');
const unfold = (value: string) => value.replace(/\r\n[ \t]/g, '');
describe('여행 내보내기와 RFC5545 경계', () => {
  it('KST 시각의 UTC 값·안정 UID와 종결 CRLF를 만든다', () => {
    const model = buildTripExport(exportSource());
    const first = buildTripCalendar(model, generated);
    const second = buildTripCalendar(model, new Date('2026-11-02T00:00:00Z'));
    const raw = unfold(first.content);
    expect(first.events).toBe(1);
    expect(first.omitted).toBe(0);
    expect(raw).toContain('DTSTART:20261105T003000Z\r\n');
    expect(raw).toContain('DTEND:20261105T020000Z\r\n');
    expect(raw).toContain('도착: 2026. 11. 05. 09:30 KST');
    expect(raw.match(/^UID:.+$/m)?.[0]).toBe(unfold(second.content).match(/^UID:.+$/m)?.[0]);
    expect(first.content).toMatch(/END:VCALENDAR\r\n$/);
    expect(first.content.replace(/\r\n/g, '')).not.toContain('\n');
  });
  it('메모의 CRLF·구분자·역슬래시를 escape해 일정 주입을 막는다', () => {
    expect(escapeCalendarText('a,b;c\\d\r\nBEGIN:VEVENT')).toBe('a\\,b\\;c\\\\d\\nBEGIN:VEVENT');
    const source = exportSource();
    source.trip.title = '여행\r\nBEGIN:VEVENT';
    source.days[0]!.note = '메모\nEND:VCALENDAR';
    const value = buildTripCalendar(buildTripExport(source), generated).content;
    expect(value.split('\r\n').filter((line) => line === 'BEGIN:VEVENT')).toHaveLength(1);
    expect(value.split('\r\n').filter((line) => line === 'END:VCALENDAR')).toHaveLength(1);
  });
  it('긴 한글·emoji를 code point 보존하며 75 UTF-8 octet에 접는다', () => {
    const text = 'DESCRIPTION:' + '한글😀é'.repeat(100);
    const folded = foldCalendarLine(text);
    for (const line of folded.split('\r\n'))
      expect(new TextEncoder().encode(line).length).toBeLessThanOrEqual(75);
    expect(unfold(folded)).toBe(text);
    expect(folded).not.toContain('�');
  });
  it('시간 미정 일정은 하루 종일·다음날 exclusive 종료를 쓴다', () => {
    const source = exportSource();
    source.days[0]!.pois[0]!.planned_arrival_at = null;
    source.days[0]!.pois[0]!.planned_departure_at = null;
    const result = buildTripCalendar(buildTripExport(source), generated);
    expect(result.content).toContain('DTSTART;VALUE=DATE:20261105');
    expect(result.content).toContain('DTEND;VALUE=DATE:20261106');
    expect(result.content).not.toContain('DTSTART:');
  });
  it('일자 override가 여행 시작일 파생보다 우선한다', () => {
    const source = exportSource();
    source.days[0]!.date = '2026-11-06';
    source.days[0]!.effective_date = '2026-11-06';
    expect(buildTripExport(source).days[0]!.date).toBe('2026-11-06');
  });
  it('날짜 미정은 추측하지 않고 실제 시각이 있는 항목만 포함한다', () => {
    const source = exportSource();
    source.trip.start_date = null;
    source.days[0]!.effective_date = null;
    let result = buildTripCalendar(buildTripExport(source), generated);
    expect(result.events).toBe(1);
    source.days[0]!.pois[0]!.planned_arrival_at = null;
    source.days[0]!.pois[0]!.planned_departure_at = null;
    result = buildTripCalendar(buildTripExport(source), generated);
    expect(result.events).toBe(0);
    expect(result.omitted).toBe(1);
  });
  it('장소가 없는 일자는 일자 메모와 함께 종일 일정으로 내보낸다', () => {
    const source = exportSource();
    source.days[0]!.pois = [];
    const result = buildTripCalendar(buildTripExport(source), generated);
    expect(result.events).toBe(1);
    expect(unfold(result.content)).toContain('일자 메모');
  });
  it('출발만 알려진 경우 그 시각을 쓰고 도착·지속 시간을 만들지 않는다', () => {
    const source = exportSource();
    source.days[0]!.pois[0]!.planned_arrival_at = null;
    const result = buildTripCalendar(buildTripExport(source), generated);
    expect(result.content).toContain('DTSTART:20261105T020000Z');
    expect(result.content).not.toContain('DTEND:');
    expect(unfold(result.content)).toContain('출발 시각만 확인된 일정');
  });
  it('도착보다 빠른 출발을 종료로 쓰지 않고 문제 개수를 알린다', () => {
    const source = exportSource();
    source.days[0]!.pois[0]!.planned_departure_at = '2026-11-05T00:00:00Z';
    const result = buildTripCalendar(buildTripExport(source), generated);
    expect(result.invalidEnds).toBe(1);
    expect(result.content).not.toContain('DTEND:');
  });
  it('조회 결과의 owner·토큰·외부URL을 넣지 않고 snapshot을 고정한다', () => {
    const source = exportSource();
    source.days[0]!.pois[0]!.user_url = 'https://example.com/?token=secret';
    const model = buildTripExport(source);
    source.trip.title = '바뀐 제목';
    source.days[0]!.note = '바뀐 메모';
    source.days[0]!.pois[0]!.title = '바뀐 장소';
    const raw = JSON.stringify(model);
    expect(raw).toContain('부산 여행');
    expect(raw).not.toContain('바뀐');
    expect(raw).not.toContain('secret');
    expect(raw).not.toContain(source.trip.owner_user_id);
  });
  it('파일명에 경로·제어 문자·공유 token을 섞을 전달 경로가 없다', () => {
    expect(exportFilename('../부산/여행\n', 'ics')).not.toMatch(/[\/\n\r]/);
    expect(exportFilename('', 'ics')).toBe('여행-일정.ics');
  });
  it('해외 브라우저 시간대에서도 한국시와 날짜를 명시한다', () => {
    expect(formatExportTime('2026-11-05T18:30:00Z')).toBe('2026. 11. 06. 03:30 KST');
    expect(formatExportTime(null)).toBe('미정');
  });
});
