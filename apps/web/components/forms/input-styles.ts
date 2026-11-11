export function inputClassName({ error, className }: { error?: boolean; className?: string } = {}) {
  return [
    'focus-ring w-full min-h-11 rounded-sm border bg-canvas px-3 py-2 text-base text-ink placeholder:text-muted',
    'transition-colors duration-normal ease-pinvi',
    'hover:border-border-strong disabled:cursor-not-allowed disabled:bg-surface-soft disabled:text-muted',
    error ? 'border-error-text' : 'border-hairline',
    className ?? '',
  ]
    .filter(Boolean)
    .join(' ');
}
