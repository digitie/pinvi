import type { TripExportModel, ExportDay } from '@/lib/tripExport';
import { formatExportTime } from '@/lib/tripExport';
import { formatTripDate, formatTripDateRange } from '@/lib/tripDateLabels';

export const TRIP_PRINT_CSS = `
.trip-print{color:#202020;background:#fff;font-size:12px;line-height:1.65;overflow-wrap:anywhere}
.trip-print h1{font-size:26px;line-height:1.35;margin:0 0 8px;font-weight:750}
.trip-print h2{font-size:18px;margin:24px 0 8px;border-top:2px solid #202020;padding-top:12px;break-after:avoid}
.trip-print p{margin:5px 0;white-space:pre-wrap}
.trip-print .trip-print-muted{color:#616161}
.trip-print .trip-print-poi{border-top:1px solid #ddd;padding:10px 0;break-inside:auto}
.trip-print .trip-print-poi p{orphans:2;widows:2}
.trip-print .trip-print-poi-heading{break-inside:avoid}
.trip-print .trip-print-with-note{break-after:avoid}
.trip-print .trip-print-poi h3{font-size:14px;margin:0;font-weight:700;break-after:avoid}
.trip-print .trip-print-map{width:100%;height:auto;max-height:280px;display:block}
.trip-print figure{margin:12px 0;break-inside:avoid}
.trip-print figcaption{font-size:10px;color:#616161}
@media print{
  @page{size:A4;margin:16mm}
  .trip-print{font-size:10pt;print-color-adjust:exact;-webkit-print-color-adjust:exact}
  .trip-print h1{font-size:21pt}
  .trip-print h2{font-size:14pt}
  .trip-print .trip-print-poi p{orphans:2;widows:2}
.trip-print .trip-print-poi-heading{break-inside:avoid}
.trip-print .trip-print-with-note{break-after:avoid}
.trip-print .trip-print-poi h3{font-size:11pt}
}
`;

function StaticDayMap({ model, day }: { model: TripExportModel; day: ExportDay }) {
  const indices = new Map(day.pois.map((poi, index) => [poi.id, index + 1]));
  const points = model.points.filter(
    (point) => point.dayIndex === day.index && indices.has(point.poiId),
  );
  if (!points.length) return null;
  // 화면 표현을 위한 Mercator 좌표. 새 주소/지역을 추정하거나 외부 지도를 호출하지 않는다.
  const projected = points.map((point) => ({
    point,
    x: (point.lon * Math.PI) / 180,
    y: -Math.log(Math.tan(Math.PI / 4 + (point.lat * Math.PI) / 360)),
  }));
  const minX = Math.min(...projected.map((point) => point.x));
  const maxX = Math.max(...projected.map((point) => point.x));
  const minY = Math.min(...projected.map((point) => point.y));
  const maxY = Math.max(...projected.map((point) => point.y));
  const scale = Math.min(
    640 / Math.max(maxX - minX, 0.00002),
    250 / Math.max(maxY - minY, 0.00002),
  );
  const positioned = projected.map(({ point, x, y }) => ({
    point,
    x: 400 + (x - (minX + maxX) / 2) * scale,
    y: 150 + (y - (minY + maxY) / 2) * scale,
  }));
  const ordered = [...positioned].sort(
    (a, b) => indices.get(a.point.poiId)! - indices.get(b.point.poiId)!,
  );
  const groups = new Map<string, typeof ordered>();
  for (const entry of ordered) {
    const key = entry.point.lon + ':' + entry.point.lat;
    const group = groups.get(key) ?? [];
    group.push(entry);
    groups.set(key, group);
  }
  return (
    <figure>
      <svg
        className="trip-print-map"
        viewBox="0 0 800 300"
        role="img"
        aria-label={`${day.index}일차 장소 위치도`}
      >
        <title>{day.index}일차 장소 위치와 방문 순서</title>
        <rect width="800" height="300" fill="#fafafa" rx="6" />
        <polyline
          points={ordered.map((point) => `${point.x},${point.y}`).join(' ')}
          fill="none"
          stroke="#9a9a9a"
          strokeWidth="2"
          strokeDasharray="5 5"
        />
        {Array.from(groups.values()).map((group) => {
          const { point, x, y } = group[0]!;
          const numbers = group.map((entry) => indices.get(entry.point.poiId)!);
          const label =
            numbers.length <= 3
              ? numbers.join('·')
              : numbers.slice(0, 2).join('·') + '+' + (numbers.length - 2);
          const width = Math.max(26, Math.min(140, label.length * 8 + 12));
          return (
            <g key={point.poiId}>
              <title>
                {group
                  .map((entry) => indices.get(entry.point.poiId) + '. ' + entry.point.title)
                  .join(', ')}
              </title>
              <rect
                x={x - width / 2}
                y={y - 13}
                width={width}
                height="26"
                rx="13"
                fill={point.color}
                stroke="white"
                strokeWidth="2"
              />
              <text
                x={x}
                y={y + 4}
                textAnchor="middle"
                fill={point.labelColor}
                fontSize={label.length > 10 ? '10' : '12'}
                fontWeight="700"
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption>
        장소 위치 개요 · 점선은 방문 순서이며 도로 경로가 아닙니다. 배경지도는 포함하지 않습니다.
        같은 좌표의 재방문 번호는 함께 표시합니다.
        {points.length < day.pois.length
          ? ` 좌표를 확인한 ${points.length}/${day.pois.length}곳을 표시했습니다.`
          : ''}
        {Array.from(groups.values())
          .filter((group) => group.length > 3)
          .map((group) => (
            <span key={group[0]!.point.poiId}>
              {' '}
              같은 위치 방문 번호: {group.map((entry) => indices.get(entry.point.poiId)).join(', ')}
              .
            </span>
          ))}
      </figcaption>
    </figure>
  );
}

export function TripExportDocument({ model }: { model: TripExportModel }) {
  return (
    <article className="trip-print" data-testid="trip-export-document">
      <style>{TRIP_PRINT_CSS}</style>
      <p className="trip-print-muted">Pinvi · 여행 일정</p>
      <h1>{model.title}</h1>
      <p>{formatTripDateRange(model.startDate, model.endDate)}</p>
      {model.description && <p>{model.description}</p>}
      {!model.days.length && <p>등록한 일자가 없습니다.</p>}
      {model.days.map((day) => (
        <section key={day.index}>
          <h2>
            {day.index}일차 · {formatTripDate(day.date)}
            {day.title ? ` · ${day.title}` : ''}
          </h2>
          {day.note && <p>{day.note}</p>}
          <StaticDayMap model={model} day={day} />
          {!day.pois.length && <p className="trip-print-muted">등록한 장소가 없습니다.</p>}
          {day.pois.map((poi, index) => (
            <article key={poi.id} className="trip-print-poi">
              <div
                className={
                  poi.note
                    ? 'trip-print-poi-heading trip-print-with-note'
                    : 'trip-print-poi-heading'
                }
              >
                <h3>
                  {index + 1}. {poi.name}
                </h3>
                <p className="trip-print-muted">
                  도착 {formatExportTime(poi.arrival)} / 출발 {formatExportTime(poi.departure)}
                </p>
                {poi.address && <p className="trip-print-muted">{poi.address}</p>}
              </div>
              {poi.note && <p>{poi.note}</p>}
            </article>
          ))}
        </section>
      ))}
    </article>
  );
}
