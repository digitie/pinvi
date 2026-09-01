/**
 * KTM `packages/kor-travel-map-admin/frontend/src/components/status-badge-variants.ts`에서 이식(T-356).
 *
 * 원문에서 바꾼 부분과 이유:
 *  - 맨 위 Hallmark 마커 주석 제거 — KTM 디자인 시스템 전용 표식.
 *  - `BadgeVariant` 타입 import 출처를 `@/components/ui/badge-variants` →
 *    `@/components/admin/ui/badge`로 바꿨다. pinvi는 admin 네임스페이스 아래에만 새 UI를 만들고,
 *    badge는 별도 작업에서 그 경로에 생긴다(KTM `badge.tsx`도 `BadgeVariant`를 재수출한다).
 *    `import type`이라 런타임 순환은 생기지 않는다.
 *  - `@/lib/status-label` → `@/lib/admin/status-label`.
 *  - 매핑 테이블 내용(5개 tone ↔ variant 1:1)은 원문 그대로다.
 *
 * ── 이하 원문 문서 주석 ──
 *
 * StatusTone → ui/badge variant 매핑(M20/M28) — 톤 테이블(`lib/admin/status-label.ts`)의 다섯 tone이
 * badge tone variant와 1:1이다. 컴포넌트 파일(`status-badge.tsx`)은 컴포넌트만 export하므로
 * (react-refresh only-export-components) 매핑 헬퍼는 여기 둔다.
 */
import type { BadgeVariant } from '@/components/admin/ui/badge';
import type { StatusTone } from '@/lib/admin/status-label';

const TONE_VARIANT: Record<StatusTone, BadgeVariant> = {
  success: 'success',
  warning: 'warning',
  destructive: 'destructive',
  info: 'info',
  neutral: 'neutral',
};

/** tone → ui/badge variant. */
export function toneBadgeVariant(tone: StatusTone): BadgeVariant {
  return TONE_VARIANT[tone];
}
