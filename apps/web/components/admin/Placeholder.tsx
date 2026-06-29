import { AdminPage, Section } from './AdminPage';

export interface PlaceholderProps {
  title: string;
  sprint: number;
  taskId?: string;
  statusLabel?: string;
  description?: string;
  notes?: string[];
}

/** Admin 기능 gap을 숨기지 않고 다음 구현 단위와 함께 표시한다. */
export function Placeholder({
  title,
  sprint,
  taskId,
  statusLabel = '구현 예정',
  description,
  notes = [],
}: PlaceholderProps) {
  return (
    <AdminPage
      title={title}
      description={description ?? `Sprint ${sprint} 후보 기능. 현재는 구현 gap으로 추적 중.`}
    >
      <Section title="작업 범위">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          {taskId && (
            <span
              className="rounded-sm border border-hairline bg-surface-soft px-2 py-1 font-semibold text-ink"
              data-testid="admin-placeholder-task"
            >
              {taskId}
            </span>
          )}
          <span className="rounded-sm bg-white px-2 py-1 text-muted">{statusLabel}</span>
          <span className="rounded-sm bg-white px-2 py-1 text-muted">S{sprint}</span>
        </div>
        <ul className="list-inside list-disc space-y-1 text-sm text-ink">
          {notes.length > 0 ? (
            notes.map((note) => <li key={note}>{note}</li>)
          ) : (
            <li className="text-muted">
              docs/execplan/admin-console-gap-plan.md의 Admin 보강 Task로 추적.
            </li>
          )}
        </ul>
      </Section>
    </AdminPage>
  );
}
