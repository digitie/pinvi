'use client';

// kor-travel-map admin `src/components/copy-button.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
//   1) **sonner 제거** — pinvi에는 `sonner`(전역 toast)가 설치돼 있지 않고 토스트 시스템 자체가 없다.
//      원문은 실패/미지원 분기에서 `toast.info` / `toast.error`로 안내했다. 그 두 분기를 컴포넌트
//      내부 상태로 옮겨, (a) 원문에 이미 있던 `aria-live="polite"` sr-only 영역이 실패 문구까지
//      읽고 (b) 버튼 라벨(`aria-label`/`title`)이 그 문구로 일시 변경되도록 했다. 즉 피드백 채널만
//      전역 toast -> 인라인으로 바뀌고, 안내 문구는 원문 그대로 유지된다.
//   2) 상태가 boolean `copied` -> `'idle' | 'copied' | 'error' | 'unsupported'` 유니온이 됐다.
//      실패 상태를 표현할 자리가 필요해서다. `data-state` 속성 이름과 `copied` 값은 그대로라
//      원문의 `data-[state=copied]:` 스타일 훅은 깨지지 않는다.
//   3) 실패/미지원일 때 아이콘을 `TriangleAlertIcon`으로 바꾸고 `data-[state=error]` /
//      `data-[state=unsupported]` 색 훅을 추가했다. toast가 없어진 만큼 실패를 색으로만 알리면
//      KTM 규율("의미가 색에만 실리지 않는다")을 어기게 된다.
//   4) 실패 문구는 성공(1.2s)보다 오래 남긴다(`FAILURE_RESET_MS` 4s) — 읽어야 할 문장이라서.
//   5) import 경로 — `@/lib/utils` -> `@/lib/admin/cn`.
//   6) 색 토큰만 pinvi 팔레트 이름으로 치환:
//        text-text-secondary -> text-body / bg-surface-subtle -> bg-admin-subtle
//        text-text-primary -> text-ink / bg-surface-muted -> bg-admin-muted
//        text-text-disabled -> text-muted-soft / text-success -> text-admin-success
//      (`rounded-control`, `duration-fast`, `outline-focus`는 pinvi에도 같은 이름이라 그대로)
//   7) 맨 위 `// Hallmark · genre: …` 마커 주석 제거, 따옴표만 pinvi prettier 설정에 맞춤.
// 히트 타깃(`size-6` + `before:-inset-2`), 전환 속성 열거, 아이콘 크기는 원문 그대로다.

import * as React from 'react';
import { CheckIcon, CopyIcon, TriangleAlertIcon } from 'lucide-react';

import { cn } from '@/lib/admin/cn';

type CopyButtonProps = {
  value: string;
  /** 접근성 이름·안내 문구에 쓰는 값 이름(예: "feature ID"). */
  label?: string;
  className?: string;
};

/** Copied glyph dwell before reverting to the copy icon (design.md: silent success, icon swap). */
const COPIED_RESET_MS = 1200;
/** 실패/미지원 안내는 읽어야 할 문장이라 성공보다 오래 남긴다. */
const FAILURE_RESET_MS = 4000;

type CopyState = 'idle' | 'copied' | 'error' | 'unsupported';

/** 상태별 안내 문구 — sr-only live 영역과 버튼 라벨이 같은 문장을 쓴다. */
const COPY_FEEDBACK: Record<Exclude<CopyState, 'idle'>, string> = {
  copied: '복사됨',
  error: '클립보드 복사에 실패했습니다. 값을 직접 선택해 복사하세요.',
  unsupported: '자동 복사를 사용할 수 없습니다. 값을 직접 선택해 복사하세요.',
};

/**
 * 클립보드 복사 버튼 (§3). settings-client의 secure-context fallback 규약을 따른다:
 * 비보안 컨텍스트/미지원 브라우저에서는 실패 대신 직접 선택 안내를 띄운다.
 *
 * Success is silent (audit M15): the icon swaps to a check for {@link COPIED_RESET_MS} and a
 * visually-hidden `aria-live` region announces `복사됨`. pinvi 이식판에서는 실패/미지원 안내도
 * 같은 live 영역 + 버튼 라벨 일시 변경으로 전달한다(전역 toast 없음).
 * Hit target: 24px box + `before:` extension to 40px (audit M23).
 */
function CopyButton({ value, label = '값', className }: CopyButtonProps) {
  const [state, setState] = React.useState<CopyState>('idle');
  const resetTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    return () => {
      if (resetTimer.current !== null) clearTimeout(resetTimer.current);
    };
  }, []);

  const flash = (next: Exclude<CopyState, 'idle'>) => {
    setState(next);
    if (resetTimer.current !== null) clearTimeout(resetTimer.current);
    resetTimer.current = setTimeout(
      () => {
        resetTimer.current = null;
        setState('idle');
      },
      next === 'copied' ? COPIED_RESET_MS : FAILURE_RESET_MS,
    );
  };

  const copy = async () => {
    if (!window.isSecureContext || !navigator.clipboard?.writeText) {
      flash('unsupported');
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
    } catch {
      flash('error');
      return;
    }
    flash('copied');
  };

  const feedback = state === 'idle' ? null : COPY_FEEDBACK[state];
  const accessibleLabel = feedback ? `${label}: ${feedback}` : `${label} 복사`;

  return (
    <button
      aria-label={accessibleLabel}
      className={cn(
        'relative inline-flex size-6 shrink-0 items-center justify-center rounded-control text-body transition-[color,background-color] duration-fast ease-out',
        'before:absolute before:-inset-2',
        'hover:bg-admin-subtle hover:text-ink active:bg-admin-muted',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus',
        'disabled:pointer-events-none disabled:text-muted-soft',
        'data-[state=copied]:text-admin-success data-[state=error]:text-admin-danger data-[state=unsupported]:text-admin-warning',
        className,
      )}
      data-state={state === 'idle' ? undefined : state}
      title={accessibleLabel}
      type="button"
      onClick={() => void copy()}
    >
      {state === 'copied' ? <CheckIcon aria-hidden className="size-3.5" /> : null}
      {state === 'error' || state === 'unsupported' ? (
        <TriangleAlertIcon aria-hidden className="size-3.5" />
      ) : null}
      {state === 'idle' ? <CopyIcon aria-hidden className="size-3.5" /> : null}
      <span aria-live="polite" className="sr-only">
        {feedback ?? ''}
      </span>
    </button>
  );
}

export { CopyButton };
export type { CopyButtonProps };
