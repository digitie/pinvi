export type MapCamera = {
  center: [number, number];
  zoom: number;
  bounds?: { ne: [number, number]; sw: [number, number] };
};

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function cameraBbox(camera: MapCamera): string | null {
  let west: number;
  let south: number;
  let east: number;
  let north: number;
  if (camera.bounds) {
    [west, south] = camera.bounds.sw;
    [east, north] = camera.bounds.ne;
  } else {
    const lonSpan = 360 / 2 ** camera.zoom;
    const latSpan = lonSpan * 1.6;
    [west, south] = [camera.center[0] - lonSpan, camera.center[1] - latSpan / 2];
    [east, north] = [camera.center[0] + lonSpan, camera.center[1] + latSpan / 2];
  }
  const w = clamp(Math.min(west, east), 124, 132);
  const e = clamp(Math.max(west, east), 124, 132);
  const s = clamp(Math.min(south, north), 33, 43);
  const n = clamp(Math.max(south, north), 33, 43);
  // 화면 전체가 국내 범위 밖이면 clamp 결과가 면적 0이다 — 요청하지 않는다.
  if (w >= e || s >= n) return null;
  return [w, s, e, n].map((v) => v.toFixed(3)).join(',');
}
