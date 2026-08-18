'use client';

import { useMemo, useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

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

  const selectField = (key: string, source: 'server' | 'mine') => {
    setSelectedMineKeys((current) => {
      const next = new Set(current);
      if (source === 'mine') next.add(key);
      else next.delete(key);
      return next;
    });
  };

  return (
    // 중첩(편집 다이얼로그 위에 뜨는 충돌 해결) 시 최상단만 Escape/Tab을 처리하도록
    // 프리미티브(useModalDialog의 modalStack)를 통해 뜬다 — 손수 만든 셸은 스택에 참여하지 못해
    // 아래 다이얼로그의 focus trap이 이 다이얼로그를 키보드로 도달 불가능하게 만들었다.
    <Dialog
      open
      onClose={onKeepEditing}
      size="lg"
      busy={saving}
      title={
        <span className="flex items-start gap-2" data-testid="conflict-title">
          <span className="mt-0.5 shrink-0 rounded-sm bg-error-bg p-1 text-error-text">
            <AlertTriangle className="size-4" aria-hidden="true" />
          </span>
          {title}
        </span>
      }
      description={description}
      testId="conflict-dialog"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={onKeepEditing} disabled={saving}>
            직접 수정 계속
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={onUseServer}
            disabled={saving}
            data-testid="conflict-use-server"
          >
            서버 값 사용
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onApply(allMineKeys)}
            disabled={saving || fields.length === 0}
            data-testid="conflict-use-mine"
          >
            내 값 전체
          </Button>
          <Button
            size="sm"
            onClick={() => onApply(selectedKeys)}
            disabled={!canApply}
            loading={saving}
            data-testid="conflict-apply-selected"
          >
            선택값 저장
          </Button>
        </>
      }
    >
      <div className="overflow-hidden rounded-sm border border-hairline">
        <div className="grid grid-cols-1 sm:grid-cols-[minmax(72px,112px)_minmax(0,1fr)_minmax(0,1fr)] bg-surface-soft text-xs font-semibold text-muted">
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
                className="grid grid-cols-1 sm:grid-cols-[minmax(72px,112px)_minmax(0,1fr)_minmax(0,1fr)] text-sm"
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
                      : 'min-h-12 bg-surface-soft px-3 py-2 text-left font-semibold text-ink ring-1 ring-inset ring-ink'
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
                      ? 'min-h-12 bg-surface-soft px-3 py-2 text-left font-semibold text-ink ring-1 ring-inset ring-ink'
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
    </Dialog>
  );
}
