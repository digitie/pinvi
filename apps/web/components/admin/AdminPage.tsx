import type { ReactNode } from 'react';

import { FilterBar as AdminFilterBar } from '@/components/admin/filter-bar';
import { SectionCard } from '@/components/admin/section-card';

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

/**
 * kor-travel-map admin의 `FilterBar`로 위임한다(T-356).
 *
 * 원래는 카드 프레임(`rounded-sm border-hairline bg-surface-soft p-3`)을 둘렀지만 KTM 툴바는
 * 프레임이 없다 — 목록 위 컨트롤 줄은 표 자신의 hairline 하나만 두고 겹치지 않는다(C3).
 * 이름과 `{children}` 시그니처를 유지해 23개 소비 페이지가 import를 바꾸지 않고 KTM 레이아웃
 * (`items-end` baseline 정렬 + `gap-x-3 gap-y-2` wrap)을 받는다.
 *
 * `items-center`→`items-end`가 핵심이다: `FilterField`가 라벨을 컨트롤 **위**에 두므로 가운데
 * 정렬하면 라벨 있는 필드와 없는 버튼의 밑선이 어긋난다.
 */
export function FilterBar({ children }: FilterBarProps) {
  return <AdminFilterBar>{children}</AdminFilterBar>;
}

export interface SectionProps {
  title: string;
  defaultCollapsed?: boolean;
  children: ReactNode;
}

/**
 * kor-travel-map admin의 `SectionCard`로 위임한다(T-357).
 *
 * `FilterBar`와 같은 방식이다 — 이름과 `{ title, children }` 시그니처를 유지해 소비 페이지
 * 20곳이 import를 바꾸지 않고 KTM 섹션 외관(Card 헤더/본문 분리, hairline 1층, `text-md`
 * 제목)을 받는다.
 *
 * 시각 차이 하나: 기존 제목은 `uppercase tracking-wide text-muted`였는데 KTM은 그런 장식을
 * 쓰지 않는다(한글 제목에 `uppercase`는 무의미하고 `tracking-wide`는 자간만 벌린다).
 * `SectionCard`의 `CardTitle`을 그대로 따른다.
 */
export function Section({ title, children }: SectionProps) {
  return <SectionCard title={title}>{children}</SectionCard>;
}
