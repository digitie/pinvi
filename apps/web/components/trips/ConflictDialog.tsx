'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';

export interface ConflictField {
  key: string;
  label: string;
  serverValue: string;
  myValue: string;
}

export interface ConflictDialogProps {
  title: string;
  description: string;
  fields: ConflictField[];
  saving?: boolean;
  onApply: (selectedKeys: string[]) => void;
  onUseServer: () => void;
  onKeepEditing: () => void;
}

export function ConflictDialog({
  title,
  description,
  fields,
  saving = false,
  onApply,
  onUseServer,
  onKeepEditing,
}: ConflictDialogProps) {
  const allMineKeys = useMemo(() => fields.map((field) => field.key), [fields]);
  const [selectedMineKeys, setSelectedMineKeys] = useState<Set<string>>(() => new Set(allMineKeys));

  const selectedKeys = Array.from(selectedMineKeys);
  const canApply = selectedKeys.length > 0;
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Move focus into the modal on open and let Escape dismiss it (a11y, T-290).
  useEffect(() => {
    dialogRef.current?.focus();
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onKeepEditing();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onKeepEditing]);

  const selectField = (key: string, source: 'server' | 'mine') => {
    setSelectedMineKeys((current) => {
      const next = new Set(current);
      if (source === 'mine') next.add(key);
      else next.delete(key);
      return next;
    });
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/45 p-4"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      data-testid="conflict-dialog"
      onClick={(event) => {
        if (event.target === event.currentTarget) onKeepEditing();
      }}
    >
      <div
        ref={dialogRef}
        tabIndex={-1}
        className="w-full max-w-2xl space-y-4 rounded-md border border-hairline bg-white p-5 shadow-lg outline-none"
      >
        <div className="flex items-start gap-3">
          <span className="mt-0.5 rounded-sm bg-error-bg p-2 text-error-text">
            <AlertTriangle className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h2 className="text-base font-bold text-ink" data-testid="conflict-title">
              {title}
            </h2>
            <p className="mt-1 text-sm text-muted">{description}</p>
          </div>
        </div>

        <div className="overflow-hidden rounded-sm border border-hairline">
          <div className="grid grid-cols-[112px_minmax(0,1fr)_minmax(0,1fr)] bg-surface-soft text-xs font-semibold text-muted">
            <span className="px-3 py-2">필드</span>
            <span className="px-3 py-2">서버 값</span>
            <span className="px-3 py-2">내 값</span>
          </div>
          <div className="divide-y divide-hairline">
            {fields.map((field) => {
              const mineSelected = selectedMineKeys.has(field.key);
              return (
                <div
                  key={field.key}
                  className="grid grid-cols-[112px_minmax(0,1fr)_minmax(0,1fr)] text-sm"
                >
                  <span className="px-3 py-3 text-xs font-semibold text-ink">{field.label}</span>
                  <button
                    type="button"
                    aria-pressed={!mineSelected}
                    onClick={() => selectField(field.key, 'server')}
                    data-testid={`conflict-field-${field.key}-server`}
                    className={
                      mineSelected
                        ? 'min-h-12 px-3 py-2 text-left text-muted hover:bg-surface-soft'
                        : 'min-h-12 bg-primary/10 px-3 py-2 text-left font-semibold text-ink ring-1 ring-inset ring-primary'
                    }
                  >
                    <span className="block break-words">{field.serverValue}</span>
                  </button>
                  <button
                    type="button"
                    aria-pressed={mineSelected}
                    onClick={() => selectField(field.key, 'mine')}
                    data-testid={`conflict-field-${field.key}-mine`}
                    className={
                      mineSelected
                        ? 'min-h-12 bg-primary/10 px-3 py-2 text-left font-semibold text-ink ring-1 ring-inset ring-primary'
                        : 'min-h-12 px-3 py-2 text-left text-muted hover:bg-surface-soft'
                    }
                  >
                    <span className="block break-words">{field.myValue}</span>
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        <div className="flex flex-wrap justify-end gap-2">
          <button
            type="button"
            onClick={onKeepEditing}
            disabled={saving}
            className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
          >
            직접 수정 계속
          </button>
          <button
            type="button"
            onClick={onUseServer}
            disabled={saving}
            data-testid="conflict-use-server"
            className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
          >
            서버 값 사용
          </button>
          <button
            type="button"
            onClick={() => onApply(allMineKeys)}
            disabled={saving || fields.length === 0}
            data-testid="conflict-use-mine"
            className="h-9 rounded-sm border border-primary px-3 text-sm font-semibold text-primary hover:bg-primary/10 disabled:opacity-50"
          >
            내 값 전체
          </button>
          <button
            type="button"
            onClick={() => onApply(selectedKeys)}
            disabled={saving || !canApply}
            data-testid="conflict-apply-selected"
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            선택값 저장
          </button>
        </div>
      </div>
    </div>
  );
}
