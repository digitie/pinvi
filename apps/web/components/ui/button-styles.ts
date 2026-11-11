export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

export type ButtonSize = 'md' | 'sm' | 'lg';

export type ButtonState = 'idle' | 'error' | 'success';

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
