'use client';

import {
  groupAccessibility,
  hasAccessibilityBadge,
  hasPetBadge,
  petPolicyLines,
  sourceAttributionLine,
  visitGuideRows,
  withDisplayKeys,
  type VisitGuideOmittable,
} from '@pinvi/domain';
import type { VisitGuide as VisitGuideData } from '@pinvi/schemas';
import { Accessibility, ChevronDown, PawPrint } from 'lucide-react';
import { useId, useState, type ReactNode } from 'react';

type Panel = 'accessibility' | 'pet';

/**
 * 배지 겸 펼침 버튼 — 색만으로 뜻을 전하지 않도록 아이콘 + 글자 + 펼침 화살표를 함께 둔다.
 */
function BadgeToggle({
  icon,
  label,
  expanded,
  controls,
  onToggle,
  testId,
}: {
  icon: ReactNode;
  label: string;
  expanded: boolean;
  controls: string;
  onToggle: () => void;
  testId: string;
}) {
  return (
    <button
      type="button"
      aria-expanded={expanded}
      // 펼친 동안에만 패널이 있으므로 그때만 가리킨다(없는 id를 가리키지 않는다).
      aria-controls={expanded ? controls : undefined}
      onClick={onToggle}
      className={`inline-flex min-h-11 items-center gap-1 rounded-sm border px-2.5 text-xs font-semibold ${
        expanded
          ? 'border-ink bg-ink text-canvas'
          : 'border-hairline text-ink hover:bg-surface-soft'
      }`}
      data-testid={testId}
    >
      <span aria-hidden="true">{icon}</span>
      {label}
      <ChevronDown
        className={`h-3.5 w-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
        aria-hidden="true"
      />
    </button>
  );
}

export interface VisitGuideProps {
  guide: VisitGuideData;
  testId: string;
  /** 같은 화면의 영업 정보 항목이 이미 보이는 줄(이용시간·휴무) — 겹치지 않게 뺀다. */
  omit?: readonly VisitGuideOmittable[];
}

/**
 * 이용 안내(Map visitor_info): 이용시간·휴무·요금·주차·예약·문의·교통·시설 등 원천 문장 그대로의 표 +
 * 무장애·반려동물 배지(눌러 펼침) + 출처(+ 기준일). 모든 문장은 텍스트로만 그리고 줄바꿈을 보존한다.
 */
export function VisitGuide({ guide, testId, omit }: VisitGuideProps) {
  const baseId = useId();
  const [open, setOpen] = useState<Panel | null>(null);
  const rows = visitGuideRows(guide, { omit });
  const accessibility = hasAccessibilityBadge(guide) ? groupAccessibility(guide.accessibility) : [];
  const pet = hasPetBadge(guide) ? petPolicyLines(guide) : [];
  if (rows.length === 0 && accessibility.length === 0 && pet.length === 0) return null;
  const toggle = (panel: Panel) => setOpen((current) => (current === panel ? null : panel));
  const accessibilityId = `${baseId}-accessibility`;
  const petId = `${baseId}-pet`;
  return (
    <div className="space-y-2" data-testid={testId} data-provider={guide.provider}>
      {rows.length > 0 && (
        <dl className="space-y-1.5 text-sm" data-testid={`${testId}-rows`}>
          {rows.map((row) => (
            <div key={row.key} data-testid={`${testId}-${row.key}`}>
              <dt className="text-xs font-semibold text-muted">{row.label}</dt>
              {withDisplayKeys(row.lines, (line) => line).map(({ item: line, key }) => (
                <dd key={key} className="whitespace-pre-line break-words text-body">
                  {line}
                </dd>
              ))}
            </div>
          ))}
        </dl>
      )}
      {(accessibility.length > 0 || pet.length > 0) && (
        <div className="flex flex-wrap gap-2" data-testid={`${testId}-badges`}>
          {accessibility.length > 0 && (
            <BadgeToggle
              icon={<Accessibility className="h-4 w-4" />}
              label="무장애 안내"
              expanded={open === 'accessibility'}
              controls={accessibilityId}
              onToggle={() => toggle('accessibility')}
              testId={`${testId}-accessibility-toggle`}
            />
          )}
          {pet.length > 0 && (
            <BadgeToggle
              icon={<PawPrint className="h-4 w-4" />}
              label="반려동물 동반"
              expanded={open === 'pet'}
              controls={petId}
              onToggle={() => toggle('pet')}
              testId={`${testId}-pet-toggle`}
            />
          )}
        </div>
      )}
      {open === 'accessibility' && accessibility.length > 0 && (
        <div
          id={accessibilityId}
          role="region"
          aria-label="무장애 안내"
          className="space-y-2 text-sm"
          data-testid={`${testId}-accessibility`}
        >
          {accessibility.map((view) => (
            <section key={view.group} aria-label={view.label}>
              <h4 className="text-xs font-semibold text-muted">{view.label}</h4>
              <ul className="space-y-0.5">
                {withDisplayKeys(view.items, (note) => `${note.facility}|${note.text}`).map(
                  ({ item, key }) => (
                    <li key={key} className="whitespace-pre-line break-words text-body">
                      <span className="font-semibold text-ink">{item.label}</span>: {item.text}
                    </li>
                  ),
                )}
              </ul>
            </section>
          ))}
        </div>
      )}
      {open === 'pet' && pet.length > 0 && (
        <dl
          id={petId}
          role="region"
          aria-label="반려동물 동반 안내"
          className="space-y-1.5 text-sm"
          data-testid={`${testId}-pet`}
        >
          {pet.map((line) => (
            <div key={line.key}>
              <dt className="text-xs font-semibold text-muted">{line.label}</dt>
              <dd className="whitespace-pre-line break-words text-body">{line.text}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="text-xs text-muted" data-testid={`${testId}-attribution`}>
        {sourceAttributionLine(guide)}
      </p>
    </div>
  );
}
