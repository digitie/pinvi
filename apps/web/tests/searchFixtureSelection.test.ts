import { describe, expect, it } from 'vitest';
import { coordinateFixtureIndex } from '../e2e-live/helpers/searchFixture';
const coord = { lon: 126.97, lat: 37.555 };
describe('근처 지도 검색 fixture 선택', () => {
  it('첫 행에 좌표가 없으면 같은 이름의 실제 point 행을 선택한다', () => {
    expect(
      coordinateFixtureIndex(
        [
          { name: '서울역', coord: null },
          { name: '서울역(경부선)', coord },
        ],
        '서울역',
      ),
    ).toBe(1);
  });
  it('첫 행이 다른 시설이면 현재 검색어의 정확한 결과를 선택한다', () => {
    expect(
      coordinateFixtureIndex(
        [
          { name: '서울역사박물관', coord },
          { name: '서울 역', coord },
        ],
        '서울역',
      ),
    ).toBe(1);
  });
  it('좌표 있는 정확 일치 fixture가 없으면 첫 행으로 대체하지 않는다', () => {
    expect(
      coordinateFixtureIndex(
        [
          { name: '서울역', coord: null },
          { name: '서울역 카페', coord },
        ],
        '서울역',
      ),
    ).toBe(-1);
  });
});
