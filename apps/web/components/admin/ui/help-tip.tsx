'use client';

import * as React from 'react';
import { CircleHelpIcon } from 'lucide-react';

import { cn } from '@/lib/admin/cn';

/**
 * KTM `src/components/help-tip.tsx`에서 이식(T-356).
 *
 * 필드 옆 도움말 아이콘 버튼. 본문 상세 설명을 인라인 hint 대신 여기로 옮긴다.
 *
 * Hit target: 24px 시각 박스 + `before:` 의사요소로 포인터 타깃을 40px까지 확장한다(14px 글리프와
 * 인라인 레이아웃은 그대로). 상태: rest ink-2 · hover/open ink on paper-2 · active paper-3 ·
 * focus는 outline recipe 1종.
 *
 * ── 원문에서 바꾼 것 ──
 * 1. **base-ui 제거**: KTM은 `Popover`(base-ui) + `Tooltip`(base-ui) 조합으로 hover 800ms 툴팁 /
 *    click 팝오버를 동시에 제공한다. pinvi에는 `@base-ui/react`가 없어 네이티브로 대체했다.
 *    - click 팝오버 → 로컬 state + 절대배치 `<div role="dialog">` (Portal/Positioner 없음).
 *    - hover 툴팁 → children이 문자열일 때만 네이티브 `title` 속성. 문자열이 아니면 hover
 *      미리보기는 사라지고 click 팝오버만 남는다(내용 접근성은 동일하게 유지).
 *    - base-ui의 `data-[starting-style]`/`data-[ending-style]` 진입·퇴장 모션 클래스는 그 상태
 *      속성을 만들어 줄 주체가 없어 제거했다.
 * 2. 팝오버 패널 클래스는 KTM `popover.tsx`의 `PopoverContent` 문자열을 그대로 쓰되 색 토큰만
 *    치환(`bg-card`→`bg-canvas`, `border-border`→`border-admin-line`, `text-text-primary`→
 *    `text-ink`, `shadow-elevated`→`shadow-card`)하고, Positioner가 없으므로 `z-50` 대신 pinvi의
 *    named z-index `z-panel` + `absolute top-full left-0 mt-2`로 위치를 잡는다.
 * 3. 트리거 색 토큰 치환: `text-text-secondary`→`text-body`, `bg-surface-subtle`→`bg-admin-subtle`,
 *    `text-text-primary`→`text-ink`, `bg-surface-muted`→`bg-admin-muted`,
 *    `text-text-disabled`→`text-muted-soft`.
 *
 * NOTE(통합): KTM `components/help-tip.tsx`를 다른 이식 작업에서 base-ui 없이 다시 포팅한다면 이
 * 파일과 중복된다. 그때는 이 파일을 지우고 form-field-* 3종의 import 경로만 바꾸면 된다.
 */
type HelpTipProps = {
  /** 도움말 대상 필드/항목 이름 — 접근성 이름 `도움말: {label}`을 만든다. */
  label: string;
  children: React.ReactNode;
  className?: string;
};

function HelpTip({ label, children, className }: HelpTipProps) {
  const [popoverOpen, setPopoverOpen] = React.useState(false);
  const rootRef = React.useRef<HTMLSpanElement>(null);

  // 팝오버 dismiss: 바깥 포인터다운 + Escape. base-ui가 해 주던 것을 최소 구현으로 대체한다.
  React.useEffect(() => {
    if (!popoverOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setPopoverOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setPopoverOpen(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [popoverOpen]);

  return (
    <span className="relative inline-flex" ref={rootRef}>
      <button
        aria-expanded={popoverOpen}
        aria-label={`도움말: ${label}`}
        className={cn(
          'relative inline-flex size-6 shrink-0 items-center justify-center rounded-control text-body transition-[color,background-color] duration-fast ease-out',
          'before:absolute before:-inset-2',
          'hover:bg-admin-subtle hover:text-ink active:bg-admin-muted aria-expanded:bg-admin-subtle aria-expanded:text-ink',
          'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
          'disabled:pointer-events-none disabled:text-muted-soft',
          className,
        )}
        onClick={() => setPopoverOpen((open) => !open)}
        title={typeof children === 'string' ? children : undefined}
        type="button"
      >
        <CircleHelpIcon aria-hidden className="size-3.5" />
      </button>
      {popoverOpen ? (
        <div
          aria-label={`도움말: ${label}`}
          className="absolute top-full left-0 z-panel mt-2 w-72 rounded-panel border border-admin-line bg-canvas p-4 text-xs leading-relaxed text-ink shadow-card focus-visible:outline-0"
          data-slot="popover-content"
          role="dialog"
        >
          {children}
        </div>
      ) : null}
    </span>
  );
}

export { HelpTip };
export type { HelpTipProps };
