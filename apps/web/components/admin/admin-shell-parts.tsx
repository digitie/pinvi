// kor-travel-map admin `src/components/admin-shell.tsx`에서 **부분만** 이식(T-356).
//
// 왜 부분 이식인가:
//   pinvi는 `app/(admin)/admin/layout.tsx`가 이미 사이드바·접힘 상태·RBAC 가드·DocumentNavLink를
//   갖춘 자체 셸을 소유한다. KTM `AdminShell`(510줄)은 nav 정본·로그아웃·rail 접힘까지 한 컴포넌트에
//   묶여 있어 통째 교체는 admin 전 페이지의 라우팅/권한 동작을 한 번에 바꾼다. 그래서 **pinvi에 대응이
//   없는 표면 조각만** 뽑았다: skip link · 헤더 밴드(제목/설명/breadcrumb/actions/meta) · rail 그리드.
//   layout.tsx는 셸 구조를 그대로 두고 skip link 배선(`AdminSkipLink` + `<main>`의
//   `id`/`tabIndex`)만 받았다.
//
// 원문에서 바꾼 부분과 이유:
//   1) nav(NAV_GROUPS)·rail 마크업·로그아웃·접힘 상태·`usePathname` 기반 section 추론을 전부 뺐다.
//      그 책임은 pinvi layout.tsx가 이미 갖는다. 그래서 `section`은 추론 없이 명시 prop만 받는다.
//   2) `withOccurrenceKeys`(KTM `@/lib/occurrence-key`)가 pinvi에 없다. breadcrumb은 위치가 곧
//      identity인 고정 배열이라 index 기반 key로 대체했다 — 같은 라벨이 두 번 나와도 충돌하지 않는다.
//      값 identity별 occurrence 유틸을 통째로 들여올 이유가 없다.
//   3) import 경로 — `@/components/ui/breadcrumb` -> `@/components/admin/ui/breadcrumb`,
//      `@/components/help-tip` -> `@/components/admin/ui/help-tip`, `@/lib/utils` -> `@/lib/admin/cn`.
//   4) 색 토큰만 pinvi 팔레트 이름으로 치환:
//        border-border -> border-admin-line / bg-card -> bg-canvas
//        text-text-primary -> text-ink / text-text-secondary -> text-body
//        shadow-elevated -> shadow-card
//      (`rounded-control`, `text-2xs`, `outline-focus`, `focus:z-50`은 pinvi에도 그대로 있다)
//   5) rail 그리드의 `var(--rail)` -> `var(--spacing-rail)`. KTM globals.css는 `:root`에 `--rail`을
//      두고 `--spacing-rail: var(--rail)`로 파생시키지만, pinvi globals.css는 `@theme`에
//      `--spacing-rail: 22rem`만 정의한다. 즉 pinvi에 `--rail`은 존재하지 않고, 정의되지 않은 var를
//      쓰면 `grid-template-columns` 선언 전체가 무효가 돼 rail 레이아웃이 조용히 사라진다.
//      값(22rem)과 의미는 동일하다.
//   6) `bleed` prop 추가(기본 off) — KTM 헤더는 `<main>` **밖**의 flush 밴드라 자체 `px-6`만 갖는다.
//      pinvi layout의 `<main>`은 이미 `px-4 py-6 sm:px-6 lg:px-8 lg:py-8`을 갖고 있어 그 안에 그냥
//      넣으면 패딩이 두 겹이 되고 hairline이 화면 끝까지 닿지 않는다. `bleed`는 그 패딩을 상쇄하는
//      정적 음수 마진만 얹어 KTM과 같은 밴드를 만든다. 원문 className 문자열 자체는 손대지 않았다.
//   7) 맨 위 `// Hallmark · genre: …` 마커 주석 제거, 따옴표만 pinvi prettier 설정에 맞춤.
//
// 런타임 값으로 Tailwind 클래스를 조립하지 않는다 — `gap`은 리터럴 클래스 3종의 정적 lookup이다.

import * as React from 'react';
import Link from 'next/link';

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/admin/ui/breadcrumb';
import { HelpTip } from '@/components/admin/ui/help-tip';
import { cn } from '@/lib/admin/cn';

/**
 * skip link의 기본 대상 id.
 *
 * `app/(admin)/admin/layout.tsx`의 `<main>`이 이 id와 `tabIndex={-1}`을 갖는다. `tabIndex`가
 * 없으면 앵커가 스크롤만 시키고 포커스는 nav에 남아 다음 Tab이 다시 nav로 들어간다 — skip link가
 * 무의미해진다.
 */
const ADMIN_MAIN_CONTENT_ID = 'admin-main-content';

type AdminSkipLinkProps = {
  /** 건너뛸 대상 요소의 id(기본 {@link ADMIN_MAIN_CONTENT_ID}). */
  targetId?: string;
  children?: React.ReactNode;
  className?: string;
};

/**
 * M11: skip link — rail의 nav 항목을 건너뛰어 본문으로. nav 밖에 둔다(링크 수 보존).
 * 평소 sr-only, 포커스를 받으면 좌상단에 카드로 나타난다.
 */
function AdminSkipLink({
  targetId = ADMIN_MAIN_CONTENT_ID,
  children = '본문으로 건너뛰기',
  className,
}: AdminSkipLinkProps) {
  return (
    <a
      className={cn(
        'sr-only focus:not-sr-only focus:fixed focus:top-3 focus:left-3 focus:z-50 focus:rounded-control focus:border focus:border-admin-line focus:bg-canvas focus:px-3 focus:py-2 focus:text-xs focus:font-medium focus:text-ink focus:shadow-card focus:outline-2 focus:outline-offset-2 focus:outline-focus',
        className,
      )}
      data-slot="admin-skip-link"
      href={`#${targetId}`}
    >
      {children}
    </a>
  );
}

type AdminBreadcrumb = { label: string; href?: string };

type AdminPageHeaderProps = {
  title: string;
  description?: string;
  /** breadcrumbs가 없을 때만 h1 위 한 줄 라벨로 렌더한다(KTM은 nav 정본에서 추론, 여기선 명시만). */
  section?: string;
  breadcrumbs?: AdminBreadcrumb[];
  help?: React.ReactNode;
  /**
   * h1 아래 한 줄 메타(상태·갱신 시각·건수 등). text-secondary 텍스트 한 줄로만 렌더한다 —
   * 제목을 반복하는 badge는 넣지 않는다(M30/M31). 구분자는 `·`.
   */
  meta?: React.ReactNode;
  /** 헤더 밴드 액션 슬롯 — primary ≤ 1 + secondary ≤ 2. 나머지 cross-link는 rail/breadcrumb로. */
  actions?: React.ReactNode;
  /**
   * pinvi `<main>`의 좌우/상단 패딩을 상쇄해 KTM과 같은 flush 밴드로 만든다.
   * layout.tsx의 `<main>` 패딩(`px-4 py-6 sm:px-6 lg:px-8 lg:py-8`)에 맞춰진 정적 값이다.
   */
  bleed?: boolean;
  className?: string;
};

/**
 * Flush header band: breadcrumb/section → h1(+help) + actions 한 baseline → meta → description,
 * 아래 hairline(M9/M30/m1).
 */
function AdminPageHeader({
  title,
  description,
  section,
  breadcrumbs,
  help,
  meta,
  actions,
  bleed = false,
  className,
}: AdminPageHeaderProps) {
  const hasBreadcrumbs = Boolean(breadcrumbs && breadcrumbs.length > 0);
  return (
    <header
      className={cn(
        'border-b border-admin-line px-6 pt-5 pb-4',
        bleed && '-mx-4 -mt-6 mb-6 sm:-mx-6 lg:-mx-8 lg:-mt-8',
        className,
      )}
      data-slot="admin-shell-header"
    >
      <div className="flex min-w-0 flex-col gap-1">
        {hasBreadcrumbs && breadcrumbs ? (
          <Breadcrumb>
            <BreadcrumbList className="text-xs">
              {breadcrumbs.map((crumb, index) => (
                // breadcrumb은 위치가 곧 identity인 고정 배열이다(KTM withOccurrenceKeys 대체).
                <React.Fragment key={`${index}:${crumb.href ?? ''}:${crumb.label}`}>
                  {index > 0 ? <BreadcrumbSeparator /> : null}
                  <BreadcrumbItem>
                    {crumb.href ? (
                      // `render`로 next/link를 넘긴다 — 맨 `<a href>`는 admin 셸을 통째로 다시
                      // 내려받는 full page reload가 된다(App Router 클라이언트 전환 상실).
                      <BreadcrumbLink render={<Link href={crumb.href} />}>
                        {crumb.label}
                      </BreadcrumbLink>
                    ) : index === breadcrumbs.length - 1 ? (
                      <BreadcrumbPage>{crumb.label}</BreadcrumbPage>
                    ) : (
                      <span>{crumb.label}</span>
                    )}
                  </BreadcrumbItem>
                </React.Fragment>
              ))}
            </BreadcrumbList>
          </Breadcrumb>
        ) : section ? (
          <p className="text-2xs font-medium text-body">{section}</p>
        ) : null}
        <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-center md:justify-between md:gap-6">
          <div className="flex min-w-0 items-center gap-2">
            <h1 className="text-xl leading-tight font-bold tracking-tight text-ink">{title}</h1>
            {help ? <HelpTip label={title}>{help}</HelpTip> : null}
          </div>
          {actions ? (
            <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
          ) : null}
        </div>
        {meta ? (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-body">
            {meta}
          </div>
        ) : null}
        {description ? <p className="max-w-3xl text-xs text-body">{description}</p> : null}
      </div>
    </header>
  );
}

/** rail 그리드의 gap — 런타임 조립 금지라 리터럴 클래스 lookup으로 둔다. */
const RAIL_GAP_CLASS = {
  4: 'gap-4',
  6: 'gap-6',
  8: 'gap-8',
} as const;

type AdminRailGridProps = {
  /** KTM 페이지들이 쓰는 값 3종(`gap-4`/`gap-6`/`gap-8`). */
  gap?: keyof typeof RAIL_GAP_CLASS;
  className?: string;
  children: React.ReactNode;
};

/**
 * 본문 + 우측 inspector rail 2열 그리드(KTM 페이지 공통 관용구
 * `grid gap-6 xl:grid-cols-[minmax(0,1fr)_var(--spacing-rail)]`). xl 미만에서는 1열로 쌓인다.
 * (주석의 클래스 예시도 Tailwind 스캔 대상이라 실제 토큰 이름을 적어야 무효 규칙이 생기지 않는다.)
 * rail 폭은 토큰 `--spacing-rail`(22rem, `w-rail`과 같은 값) 하나에서 온다.
 */
function AdminRailGrid({ gap = 6, className, children }: AdminRailGridProps) {
  return (
    <div
      className={cn(
        'grid',
        RAIL_GAP_CLASS[gap],
        'xl:grid-cols-[minmax(0,1fr)_var(--spacing-rail)]',
        className,
      )}
      data-slot="admin-rail-grid"
    >
      {children}
    </div>
  );
}

export { ADMIN_MAIN_CONTENT_ID, AdminPageHeader, AdminRailGrid, AdminSkipLink };
export type { AdminBreadcrumb, AdminPageHeaderProps, AdminRailGridProps, AdminSkipLinkProps };
