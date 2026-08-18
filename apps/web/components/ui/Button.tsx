/* Hallmark · component: button · genre: modern-minimal · theme: pinvi-locked(DESIGN.md)
 * states: default · hover · focus · active · disabled · loading · error · success
 * contrast: cta/white 4.9:1 · secondary ink/white 15.9:1 · danger error-text/white 5.5:1
 */
import Link, { type LinkProps } from 'next/link';
import { Loader2 } from 'lucide-react';
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react';
import { forwardRef } from 'react';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'md' | 'sm' | 'lg';
/** 문맥 상태 — 폼 제출 실패/성공 직후의 조용한 표시(색·아이콘 없이 테두리/톤만). */
export type ButtonState = 'idle' | 'error' | 'success';

/**
 * 웹 버튼 프리미티브(DESIGN.md "Hallmark 잠금 시스템" CTA voice). 페이지는 className을 재조립하지 않고
 * variant/size만 고른다. 8상태: default·hover·focus-visible(outline)·active·disabled(3채널: 배경·커서·aria)
 * ·loading(aria-busy + 스피너, 라벨 유지)·error·success(data-state).
 * - primary = 채운 CTA. 배경은 `cta`(#e00b41, white 4.9:1) — Rausch #ff385c는 white 라벨 대비 미달이라 쓰지 않는다.
 * - 44px(min-h-11)이 기본. `sm`은 밀도 높은 표/툴바 전용이고 coarse pointer(터치)에서는 44px로 승격.
 * - 모션은 색만 200ms; overshoot·scale 없음. focus 링은 outline(즉시).
 */
export function buttonClassName({
  variant = 'primary',
  size = 'md',
  fullWidth = false,
  className,
}: {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  className?: string;
} = {}): string {
  const base =
    'focus-ring inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-sm font-semibold ' +
    'transition-colors duration-normal ease-pinvi disabled:cursor-not-allowed ' +
    'aria-busy:cursor-progress data-[state=error]:outline data-[state=error]:outline-2 data-[state=error]:outline-error-text ' +
    'data-[state=success]:outline data-[state=success]:outline-2 data-[state=success]:outline-success-text';
  const sizes: Record<ButtonSize, string> = {
    md: 'min-h-11 px-5 text-base',
    sm: 'min-h-9 px-3 text-sm [@media(pointer:coarse)]:min-h-11',
    lg: 'min-h-12 px-6 text-base',
  };
  const variants: Record<ButtonVariant, string> = {
    primary:
      'bg-cta text-on-primary hover:bg-cta-hover active:bg-cta-hover ' +
      // disabled = 옅은 tint + 진한 라벨(white는 1.5:1로 안 읽힘) — 어떤 액션이 잠겼는지 남긴다.
      'disabled:bg-primary-disabled disabled:text-cta-hover',
    secondary:
      'border border-ink bg-canvas text-ink hover:bg-surface-soft active:bg-surface-strong ' +
      'disabled:border-hairline disabled:text-muted-soft disabled:bg-canvas',
    ghost:
      'text-ink hover:bg-surface-soft active:bg-surface-strong disabled:text-muted-soft disabled:bg-transparent',
    danger:
      'bg-error-text text-on-primary hover:bg-error-text-hover active:bg-error-text-hover ' +
      'disabled:bg-error-bg disabled:text-muted',
  };
  return [base, sizes[size], variants[variant], fullWidth ? 'w-full' : '', className ?? '']
    .filter(Boolean)
    .join(' ');
}

interface CommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  fullWidth?: boolean;
  /** 진행 중 — aria-busy + 스피너, 라벨은 유지(레이아웃 시프트 없음), 클릭 차단. */
  loading?: boolean;
  /** 조용한 문맥 상태 — 실패/성공 직후 outline 톤. 색만으로 전달하지 않도록 옆에 텍스트를 둔다. */
  state?: ButtonState;
  leadingIcon?: ReactNode;
  children: ReactNode;
}

export type ButtonProps = CommonProps & Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'>;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant,
    size,
    fullWidth,
    loading = false,
    state = 'idle',
    leadingIcon,
    className,
    children,
    disabled,
    type = 'button',
    ...rest
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={buttonClassName({ variant, size, fullWidth, className })}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      aria-disabled={disabled || loading || undefined}
      data-state={state === 'idle' ? undefined : state}
      {...rest}
    >
      {loading ? (
        <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden="true" />
      ) : leadingIcon ? (
        <span className="inline-flex shrink-0 [&>svg]:size-4" aria-hidden="true">
          {leadingIcon}
        </span>
      ) : null}
      <span className="min-w-0">{children}</span>
    </button>
  );
});

export type ButtonLinkProps = CommonProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href' | 'children'> &
  Pick<LinkProps, 'href' | 'prefetch' | 'replace' | 'scroll'>;

/** 버튼 모양 링크(next/link). 탐색 액션은 `<a>`, 상태 변경은 `<Button>` — 역할을 섞지 않는다. */
export function ButtonLink({
  variant,
  size,
  fullWidth,
  loading = false,
  state = 'idle',
  leadingIcon,
  className,
  children,
  href,
  ...rest
}: ButtonLinkProps) {
  return (
    <Link
      href={href}
      className={buttonClassName({ variant, size, fullWidth, className })}
      aria-busy={loading || undefined}
      data-state={state === 'idle' ? undefined : state}
      {...rest}
    >
      {loading ? (
        <Loader2 className="size-4 shrink-0 animate-spin" aria-hidden="true" />
      ) : leadingIcon ? (
        <span className="inline-flex shrink-0 [&>svg]:size-4" aria-hidden="true">
          {leadingIcon}
        </span>
      ) : null}
      <span className="min-w-0">{children}</span>
    </Link>
  );
}
