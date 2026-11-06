import { expect, it } from 'vitest';
import { viewportBboxMatches } from '../e2e-live/helpers/viewportBbox';

it('한국 바깥으로 넓어진 native viewport도 정당하게 clamp한 API 경계와 일치한다', () => {
  expect(viewportBboxMatches([124, 33, 132, 43], [120, 30, 140, 45], 7)).toBe(true);
  expect(viewportBboxMatches([125, 33, 132, 43], [120, 30, 140, 45], 7)).toBe(false);
});

it('바깥 양자화 오차는 허용하되 이전 카메라의 응답은 거절한다', () => {
  expect(viewportBboxMatches([128.439, 36.485, 128.934, 37.34],
    [128.43941, 36.48518, 128.93317, 37.33953], 9)).toBe(true);
  expect(viewportBboxMatches([128.2, 36.48, 128.7, 37.34],
    [128.43941, 36.48518, 128.93317, 37.33953], 9)).toBe(false);
});
