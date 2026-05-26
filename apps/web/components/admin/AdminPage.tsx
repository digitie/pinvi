import type { ReactNode } from 'react';

export interface AdminPageProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}

/** SPEC V8 M-3 — Admin 공통 페이지 chrome. */
export function AdminPage({ title, description, actions, children }: AdminPageProps) {
  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">{title}</h1>
          {description && <p className="mt-1 text-sm text-muted">{description}</p>}
        </div>
        {actions && <div className="flex gap-2">{actions}</div>}
      </header>
      {children}
    </div>
  );
}

export interface FilterBarProps {
  children: ReactNode;
}

export function FilterBar({ children }: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-sm border border-hairline bg-surface-soft p-3">
      {children}
    </div>
  );
}

export interface SectionProps {
  title: string;
  defaultCollapsed?: boolean;
  children: ReactNode;
}

export function Section({ title, children }: SectionProps) {
  return (
    <section className="space-y-3 rounded-sm border border-hairline bg-white p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2>
      <div>{children}</div>
    </section>
  );
}
