// kor-travel-map admin `src/components/filter-bar.tsx`에서 이식(T-356).
//
// 원문에서 바꾼 부분과 이유:
// - 맨 위 `// Hallmark · genre: …` 마커 주석 제거 — KTM `design.md` 전용 표식이다.
// - `@/lib/utils` → `@/lib/admin/cn`.
// - 문자열 따옴표를 pinvi prettier 설정(`singleQuote: true`)에 맞춰 작은따옴표로 바꿨다.
// - 색 토큰 치환표만 적용(레이아웃/간격/타이포 클래스는 원문 그대로):
//   `text-text-secondary`→`text-body`, `text-text-tertiary`→`text-muted`.
//   `text-2xs`는 pinvi에 같은 이름·같은 값(12px)으로 등록돼 있어 그대로 쓴다.
// - `'use client'`는 붙이지 않는다 — 상태·이벤트 없는 순수 표시 컴포넌트다(card/alert와 동일).
//
// NOTE(소비처): pinvi에는 `components/admin/AdminPage.tsx`가 export하는 **다른** `FilterBar`가
// 이미 있고 23개 admin 페이지가 그것을 쓴다. 시그니처가 달라(`{ children }`만 받고 카드 프레임을
// 두른다) 여기서 합치지 않는다. 소비처 전환은 후속 단계에서 한 화면씩 한다.
import * as React from 'react';

import { cn } from '@/lib/admin/cn';

/**
 * 목록 상단 툴바의 유일한 필터 idiom(M26). 모든 컨트롤을 `FilterField`(가시 라벨 위·컨트롤 아래)로
 * 감싼다 — placeholder는 형식만 보여 주고 라벨을 대신하지 않는다. 행은 wrap(가로 스크롤 금지),
 * 정렬은 column header에만, page-size는 pager 쪽에 둔다.
 */
function FilterBar({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('flex flex-wrap items-end gap-x-3 gap-y-2', className)}
      data-slot="filter-bar"
      {...props}
    />
  );
}

/**
 * 라벨 + 컨트롤 결합. 라벨은 12px/500 secondary. `htmlFor`를 주면 label이 컨트롤을 가리키고,
 * 생략하면 label이 컨트롤을 감싼다(native input/select에 적합).
 * `hint`는 컨트롤 아래 한 줄(형식 안내·disabled 사유 — 색만으로 알리지 않는다).
 */
function FilterField({
  label,
  htmlFor,
  hint,
  className,
  children,
}: {
  label: string;
  htmlFor?: string;
  /** 컨트롤 아래 한 줄 보조 문구(형식/사유). */
  hint?: React.ReactNode;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label
      className={cn('flex min-w-0 flex-col gap-1', className)}
      data-slot="filter-field"
      htmlFor={htmlFor}
    >
      <span className="text-2xs leading-none font-medium text-body">{label}</span>
      {children}
      {hint ? <span className="text-2xs text-muted">{hint}</span> : null}
    </label>
  );
}

/** 툴바 우측 액션 묶음(적용/초기화 등) — FilterBar 안에서 컨트롤과 baseline을 맞춘다. */
function FilterActions({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      className={cn('flex flex-wrap items-center gap-2 self-end', className)}
      data-slot="filter-actions"
      {...props}
    />
  );
}

export { FilterActions, FilterBar, FilterField };
