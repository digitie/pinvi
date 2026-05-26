import { AdminPage, Section } from './AdminPage';

export interface PlaceholderProps {
  title: string;
  sprint: number;
  description?: string;
  notes?: string[];
}

/** Sprint 3에서는 미구현. Sprint 5/6에서 결선될 페이지 stub. */
export function Placeholder({ title, sprint, description, notes = [] }: PlaceholderProps) {
  return (
    <AdminPage
      title={title}
      description={description ?? `Sprint ${sprint}에서 결선 예정. 현재는 skeleton.`}
    >
      <Section title="작업 범위">
        <ul className="list-inside list-disc space-y-1 text-sm text-ink">
          {notes.length > 0 ? (
            notes.map((note) => <li key={note}>{note}</li>)
          ) : (
            <li className="text-muted">SPEC V8 M-2 / `docs/api/admin.md` 참조.</li>
          )}
        </ul>
      </Section>
    </AdminPage>
  );
}
