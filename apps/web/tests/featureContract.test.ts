import { describe, expect, it } from 'vitest';
import {
  FeatureDetailCardSchema,
  FeatureDetailSchema,
  FeatureSummarySchema,
} from '@pinvi/schemas';

/**
 * T-VN-42 — 공개 `status` 제거 회귀 게이트(프런트 미러).
 *
 * Map 3축 feature state cutover(`1f2bdc3a`)로 user 표면에서 사라진 `status`를 서버 계약
 * (`apps/api/app/schemas/feature.py`)과 함께 Zod 미러에서도 제거했다. 서버 쪽 게이트는
 * `apps/api/tests/unit/test_feature_schemas.py`(선언 등호 + OpenAPI 노출)가 맡고, 여기서는
 * 클라이언트 파싱 계약을 고정한다.
 *
 * Zod 기본값은 strip이라 `status`를 넣어도 **예외가 아니라 조용한 무시**가 된다. 그래서 파싱
 * 예외가 아니라 **결과 키 부재**로 검사해야 회귀가 잡힌다.
 *
 * 이 파일이 `apps/web/tests`에 있는 이유는 CI다 — `web.yml`의 `npm test --workspace @pinvi/web`이
 * 이 디렉터리만 실행한다. `packages/schemas`에 두면 관례상 더 맞지만 CI가 그 워크스페이스의
 * vitest를 호출하지 않아 영원히 실행되지 않는 테스트가 된다.
 */

const VALID_SUMMARY = {
  feature_id: 'place:1',
  kind: 'place',
  name: '경복궁',
  coord: { lon: 126.977, lat: 37.5796 },
  category: '관광명소',
  marker_color: 'P-13',
  marker_icon: 'marker',
};

describe('feature 공개 계약 — status 제거', () => {
  it('FeatureSummarySchema의 필드 집합이 정확히 고정된다', () => {
    // 등호로 못박는다: `status`만 막으면 `feature_status`/`state` 같은 다른 이름의 재도입을 놓친다.
    expect(Object.keys(FeatureSummarySchema.shape).sort()).toEqual(
      [
        'feature_id',
        'kind',
        'name',
        'coord',
        'category',
        'marker_color',
        'marker_icon',
        'distance_m',
      ].sort(),
    );
  });

  it('FeatureDetailSchema에 status가 없다', () => {
    expect(Object.keys(FeatureDetailSchema.shape)).not.toContain('status');
  });

  it('detail-card 7개 arm 전부에 status가 없다', () => {
    const arms = FeatureDetailCardSchema.options;
    expect(arms).toHaveLength(7);
    for (const arm of arms) {
      const kind = (arm.shape.kind as { value: string }).value;
      expect(Object.keys(arm.shape), kind).not.toContain('status');
    }
  });

  it('서버가 status를 다시 보내도 파싱 결과에 키가 남지 않는다', () => {
    // 배포 순서상 구 서버 응답이 먼저 도착할 수 있다 — strip 동작을 계약으로 고정한다.
    const parsed = FeatureSummarySchema.parse({ ...VALID_SUMMARY, status: 'active' });
    expect(parsed).not.toHaveProperty('status');
  });
});
