/**
 * 여행 지도 시점 계산 — 장소들을 모두 담는 중심·줌.
 *
 * `vworld-map-rn`은 `initialCenter`/`initialZoom`을 mount 때 한 번만 읽고 map-ready 콜백이 없다. 그래서 **첫 시점**은
 * 지도 크기(dp)를 아는 화면이 직접 계산한다. 뜬 뒤의 맞춤은 `fitBounds({ paddingPx })`(rn 1.0.2부터 네이티브도
 * 여백을 지킨다)를 쓰고, 이 계산은 최대 줌을 넘는 좁은 범위인지 판단할 때만 함께 쓴다. MapLibre(웹·네이티브)
 * 줌 0의 세계 폭은 512 단위다.
 */

const WORLD_SIZE_AT_ZOOM_0 = 512;

export type CameraPadding = { top: number; right: number; bottom: number; left: number };

export type CameraTarget = { center: [number, number]; zoom: number };

export interface FitCameraOptions {
  /** 장소가 한 곳(또는 같은 자리)뿐일 때의 줌. */
  singlePointZoom?: number;
  minZoom?: number;
  maxZoom?: number;
}

/** 경도·위도 → Web Mercator 정규 좌표(0..1, y는 북쪽이 0). */
function project(lon: number, lat: number): [number, number] {
  const clampedLat = Math.max(-85.05112878, Math.min(85.05112878, lat));
  const sin = Math.sin((clampedLat * Math.PI) / 180);
  const x = (lon + 180) / 360;
  const y = 0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI);
  return [x, y];
}

function unproject(x: number, y: number): [number, number] {
  const lon = x * 360 - 180;
  const n = Math.PI - 2 * Math.PI * y;
  const lat = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  return [lon, lat];
}

function round(value: number, digits: number): number {
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

/**
 * 좌표들을 지도 크기(`size`, dp)에서 여백(`padding`) 안쪽에 모두 담는 중심·줌. 여백이 비대칭이면
 * (위에 칩 줄 등) 중심을 그만큼 옮긴다. 좌표가 없으면 null.
 */
export function fitCameraToPoints(
  points: ReadonlyArray<{ lon: number; lat: number }>,
  size: { width: number; height: number },
  padding: CameraPadding,
  { singlePointZoom = 14, minZoom = 5, maxZoom = 16 }: FitCameraOptions = {},
): CameraTarget | null {
  const first = points[0];
  if (!first) return null;
  let [minX, minY] = project(first.lon, first.lat);
  let [maxX, maxY] = [minX, minY];
  for (const p of points) {
    const [x, y] = project(p.lon, p.lat);
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  const innerWidth = Math.max(1, size.width - padding.left - padding.right);
  const innerHeight = Math.max(1, size.height - padding.top - padding.bottom);
  const spanX = maxX - minX;
  const spanY = maxY - minY;
  let zoom: number;
  if (spanX === 0 && spanY === 0) {
    zoom = singlePointZoom;
  } else {
    const zoomX = spanX > 0 ? Math.log2(innerWidth / (WORLD_SIZE_AT_ZOOM_0 * spanX)) : Infinity;
    const zoomY = spanY > 0 ? Math.log2(innerHeight / (WORLD_SIZE_AT_ZOOM_0 * spanY)) : Infinity;
    zoom = Math.min(zoomX, zoomY, singlePointZoom + 2);
  }
  zoom = Math.max(minZoom, Math.min(maxZoom, zoom));
  // 담을 상자의 중심이 여백 안쪽 상자의 중심에 오도록, 지도 중심을 여백 차이의 절반만큼 반대로 옮긴다.
  const worldSize = WORLD_SIZE_AT_ZOOM_0 * 2 ** zoom;
  const offsetX = (padding.right - padding.left) / 2 / worldSize;
  const offsetY = (padding.bottom - padding.top) / 2 / worldSize;
  const [lon, lat] = unproject((minX + maxX) / 2 + offsetX, (minY + maxY) / 2 + offsetY);
  return { center: [round(lon, 6), round(lat, 6)], zoom: round(zoom, 2) };
}
