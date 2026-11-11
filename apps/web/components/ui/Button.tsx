/* Hallmark · component: button · genre: modern-minimal · theme: pinvi-locked(DESIGN.md)
 * states: default · hover · focus · active · disabled · loading · error · success
 * contrast: cta/white 4.9:1 · secondary ink/white 15.9:1 · danger error-text/white 5.5:1
 */
import {
  type ButtonSize,
  type ButtonState,
  type ButtonVariant,
  buttonClassName,
} from '@/components/ui/button-styles';
import { Loader2 } from 'lucide-react';
import Link, { type LinkProps } from 'next/link';
import type { AnchorHTMLAttributes, ButtonHTMLAttributes, ReactNode } from 'react';
import { forwardRef } from 'react';

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
