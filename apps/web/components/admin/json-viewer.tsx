// kor-travel-map admin `src/components/json-viewer.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) import 경로 — `@/components/copy-button` -> `@/components/admin/copy-button`,
//      `@/lib/format` -> `@/lib/admin/format`, `@/lib/utils` -> `@/lib/admin/cn`.
//   2) 맨 위 `// Hallmark · genre: …` 마커 주석 제거 — KTM design.md 전용 표식.
//   3) 색 토큰만 pinvi 팔레트 이름으로 치환:
//        border-border -> border-admin-line / bg-surface-subtle -> bg-admin-subtle
//        text-text-primary -> text-ink / text-text-tertiary -> text-muted
//        border-destructive -> border-admin-danger / bg-destructive-tint -> bg-admin-danger-tint
//        text-destructive -> text-admin-danger
//   4) 문서 주석의 "Geist Mono 12px"를 pinvi 스택 표현으로 고쳤다 — pinvi mono는 preset이 소유한
//      시스템 mono 스택(ui-monospace/SF Mono/Menlo/Consolas)이고 Geist를 로드하지 않는다.
//      클래스(`font-mono text-2xs`)는 그대로라 치수·자간 규약은 동일하다.
//   5) 따옴표만 pinvi prettier 설정에 맞췄다.
// `max-h-40 / max-h-72 / max-h-[32rem]` 3단, `break-all whitespace-pre-wrap slashed-zero`,
// 복사 버튼 오버레이(`pr-10` + `absolute top-2 right-2`), `stringify` 로직은 원문 그대로다.
//
// 주의: `maxHeight`는 정적 클래스 3종 중 하나를 고르는 리터럴 분기다 — 런타임 값으로
// `max-h-[${x}]`를 조립하지 않는다(Tailwind 정적 추출 불가, 1단계 실회귀).

import { CopyButton } from '@/components/admin/copy-button';
import { NULL_GLYPH } from '@/lib/admin/format';
import { cn } from '@/lib/admin/cn';

type JsonViewerProps = {
  value: unknown;
  maxHeight?: 'sm' | 'md' | 'lg';
  tone?: 'default' | 'destructive';
  /** true면 우상단에 복사 버튼. */
  copyable?: boolean;
  className?: string;
  'aria-label'?: string;
};

function stringify(value: unknown): string {
  if (value === null || value === undefined) return NULL_GLYPH;
  if (typeof value === 'string') {
    try {
      return JSON.stringify(JSON.parse(value), null, 2);
    } catch {
      return value;
    }
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/**
 * JSON/raw payload 표시 표준 블록 — 그룹 안의 유일한 JSON 렌더러(M42).
 * mono 12px, `admin-subtle` 표면 위 hairline, 값 없음은 `—`.
 */
function JsonViewer({
  value,
  maxHeight = 'md',
  tone = 'default',
  copyable = false,
  className,
  'aria-label': ariaLabel,
}: JsonViewerProps) {
  const text = stringify(value);
  const isEmpty = text === NULL_GLYPH;
  return (
    <div className={cn('relative min-w-0', className)} data-slot="json-viewer">
      <pre
        aria-label={ariaLabel}
        className={cn(
          'overflow-auto rounded-control border p-3 font-mono text-2xs leading-relaxed break-all whitespace-pre-wrap slashed-zero',
          tone === 'default' && 'border-admin-line bg-admin-subtle text-ink',
          tone === 'destructive' && 'border-admin-danger bg-admin-danger-tint text-admin-danger',
          isEmpty && 'text-muted',
          copyable && !isEmpty && 'pr-10',
          maxHeight === 'sm' && 'max-h-40',
          maxHeight === 'md' && 'max-h-72',
          maxHeight === 'lg' && 'max-h-[32rem]',
        )}
      >
        {text}
      </pre>
      {copyable && !isEmpty ? (
        <div className="absolute top-2 right-2">
          <CopyButton label="JSON" value={text} />
        </div>
      ) : null}
    </div>
  );
}

export { JsonViewer };
export type { JsonViewerProps };
