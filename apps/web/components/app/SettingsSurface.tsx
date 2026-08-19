import type { ReactNode } from 'react';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(app) · design-system: DESIGN.md
 * 설정 화면 전용 표면 — 관리자 chrome(uppercase eyebrow h2 · 12px 표 헤더 · 카드 안 카드)을 쓰지 않는다.
 * 섹션은 hairline rule로 나누고, 목록은 표가 아니라 hairline row divider 리스트다.
 */

export interface SettingsSectionProps {
  title: string;
  /** 제목 아래 한 줄 설명(선택). */
  description?: ReactNode;
  /** 제목 줄 우측 액션(선택). */
  actions?: ReactNode;
  children: ReactNode;
}

export function SettingsSection({ title, description, actions, children }: SettingsSectionProps) {
  return (
    <section className="space-y-3 border-t border-hairline pt-6 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-ink">{title}</h2>
          {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export interface SettingsListProps<T> {
  items: T[];
  /** 행 key. */
  rowKey: (item: T) => string;
  /** 행 본문 — 주 라벨/보조 텍스트는 호출부가 구성한다. */
  renderRow: (item: T) => ReactNode;
  /** 행 우측 액션(선택). */
  renderActions?: (item: T) => ReactNode;
  /** 행에 붙일 testid(선택) — 기존 e2e 계약 유지용. */
  rowTestId?: (item: T) => string;
  loading?: boolean;
  /** 비었을 때 문구 + 다음 행동. */
  empty?: ReactNode;
  'aria-label'?: string;
}

export function SettingsList<T>({
  items,
  rowKey,
  renderRow,
  renderActions,
  rowTestId,
  loading = false,
  empty,
  'aria-label': ariaLabel,
}: SettingsListProps<T>) {
  if (loading) {
    // 형태가 정해진 목록은 spinner가 아니라 skeleton(DESIGN.md 상태 UI).
    return (
      <div className="divide-y divide-hairline border-y border-hairline" aria-busy="true">
        <span className="sr-only">불러오는 중…</span>
        {[0, 1, 2].map((row) => (
          <div key={row} className="animate-pulse space-y-2 py-4">
            <div className="h-4 w-2/5 rounded-sm bg-surface-strong" />
            <div className="h-3 w-3/5 rounded-sm bg-surface-soft" />
          </div>
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return <div className="border-y border-hairline py-6 text-sm text-muted">{empty}</div>;
  }

  return (
    <ul
      className="m-0 list-none divide-y divide-hairline border-y border-hairline p-0"
      aria-label={ariaLabel}
    >
      {items.map((item) => (
        <li
          key={rowKey(item)}
          data-testid={rowTestId?.(item)}
          className="flex flex-wrap items-start justify-between gap-3 py-4"
        >
          <div className="min-w-0 flex-1">{renderRow(item)}</div>
          {renderActions ? (
            <div className="flex shrink-0 items-center gap-2">{renderActions(item)}</div>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
