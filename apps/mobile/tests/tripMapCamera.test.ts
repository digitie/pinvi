import { describe, expect, it } from 'vitest';
import { fitCameraToPoints } from '../lib/tripMapCamera';

const SIZE = { width: 400, height: 400 };
const NO_PADDING = { top: 0, right: 0, bottom: 0, left: 0 };

describe('fitCameraToPoints', () => {
  it('좌표가 없으면 null', () => {
    expect(fitCameraToPoints([], SIZE, NO_PADDING)).toBeNull();
  });

  it('한 곳(또는 같은 자리)이면 그 좌표를 가운데로, 한 곳 줌', () => {
    expect(fitCameraToPoints([{ lon: 127, lat: 37.5 }], SIZE, NO_PADDING)).toEqual({
      center: [127, 37.5],
      zoom: 14,
    });
    expect(
      fitCameraToPoints(
        [
          { lon: 127, lat: 37.5 },
          { lon: 127, lat: 37.5 },
        ],
        SIZE,
        NO_PADDING,
        { singlePointZoom: 13 },
      )?.zoom,
    ).toBe(13);
  });

  it('경도 폭이 지도 폭을 채우는 줌을 고른다(줌 0 세계 폭 512)', () => {
    // 경도 1.40625° = 세계의 1/256 → 줌 z에서 512·2^z/256 = 2^(z+1) px. 400px을 채우면 z = log2(200).
    const camera = fitCameraToPoints(
      [
        { lon: 127, lat: 37.5 },
        { lon: 128.40625, lat: 37.5 },
      ],
      SIZE,
      NO_PADDING,
    );
    expect(camera?.zoom).toBeCloseTo(Math.log2(200), 2);
    expect(camera?.center[0]).toBeCloseTo(127.703125, 5);
  });

  it('여백만큼 줌을 낮추고, 위 여백이 크면 중심을 위로 옮겨 장소를 아래쪽 빈 곳에 둔다', () => {
    const points = [
      { lon: 126.9, lat: 37.4 },
      { lon: 127.1, lat: 37.6 },
    ];
    const plain = fitCameraToPoints(points, SIZE, NO_PADDING);
    const padded = fitCameraToPoints(points, SIZE, { top: 80, right: 20, bottom: 20, left: 20 });
    expect(plain && padded).toBeTruthy();
    expect(padded!.zoom).toBeLessThan(plain!.zoom);
    expect(padded!.center[1]).toBeGreaterThan(plain!.center[1]);
    expect(padded!.center[0]).toBeCloseTo(plain!.center[0], 6);
  });

  it('줌은 최소·최대 안으로 자른다', () => {
    const far = fitCameraToPoints(
      [
        { lon: 125, lat: 33.5 },
        { lon: 131, lat: 38.5 },
      ],
      { width: 100, height: 100 },
      NO_PADDING,
      { minZoom: 5 },
    );
    expect(far?.zoom).toBe(5);
    const near = fitCameraToPoints(
      [
        { lon: 127, lat: 37.5 },
        { lon: 127.00001, lat: 37.5 },
      ],
      SIZE,
      NO_PADDING,
    );
    expect(near?.zoom).toBe(16);
  });
});
