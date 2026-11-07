import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * #700 (CORE-023·SRCH-044): 열린 지도 popup의 '상세보기'를 이웃 마커가 덮었다.
 *
 * maplibre는 마커를 `.maplibregl-canvas-container` 안에, popup은 그 형제(`.maplibregl-map` 직속)로 붙인다.
 * vworld-map-web `Marker`는 클릭된 마커에 inline z-index를 전역 카운터로 준다(1001부터 클릭마다 +1).
 * canvas container가 쌓임 맥락이 아니면 그 마커와 popup(`.pinvi-map-popup` z20)이 같은 맥락에서 겨뤄
 * 마커가 이긴다. jsdom은 쌓임을 계산하지 않으므로 그 경계를 만드는 CSS 규칙 자체를 잠근다.
 */
const CSS = readFileSync(join(process.cwd(), 'app/globals.css'), 'utf8');

function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp(`(^|\\n)${escaped}\\s*\\{([^}]*)\\}`).exec(CSS);
  if (!match) throw new Error(`규칙을 찾지 못했다: ${selector}`);
  return match[2] ?? '';
}

describe('지도 popup은 모든 마커 위에 쌓인다 (#700)', () => {
  it('canvas container가 독립 쌓임 맥락이라 마커 z-index가 popup과 겨루지 않는다', () => {
    expect(rule('.maplibregl-canvas-container')).toMatch(/isolation:\s*isolate/);
  });

  it('선택 popup은 쌓임 맥락이 된 canvas container(z 0)와 앱 지도 패널(z10)보다 위다', () => {
    const zIndex = /z-index:\s*(\d+)/.exec(rule('.pinvi-map-popup'));
    expect(zIndex).not.toBeNull();
    expect(Number(zIndex![1])).toBeGreaterThan(10);
  });
});
