import type { StatusTone } from '@/lib/admin/status-label';

/** 도메인의 destructive 상태를 공통 Badge의 error tone에 연결한다. */
export function toneBadgeTone(tone: StatusTone): string {
  return tone === 'destructive' ? 'error' : tone;
}
