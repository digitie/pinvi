import type { ReactNode } from 'react';
import { PublicColophon, PublicMasthead } from '@/components/app/PublicChrome';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(폼 표면) · design-system: DESIGN.md · designed-as-app
 * nav: N1(워드마크만 — 폼 자체가 로그인/가입 CTA) · footer: Ft2 · enrichment: none
 * removed: 회색 좌패널의 스캐폴딩 문구("v1.0 출시 전 — Sprint 1 scaffolding"), h2>h1 순서 역전
 */
const FACTS = [
  '국내 지도·장소 검색으로 일자별 계획',
  '메모·예산·첨부와 날씨·공휴일 기록',
  '읽기 전용 링크와 동행자 초대로 공유',
];

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas text-ink">
      <PublicMasthead />
      <div className="mx-auto grid w-full max-w-6xl flex-1 gap-12 px-6 py-10 md:grid-cols-12 md:py-16">
        {/* 좌: flat 문장 패널(카드·회색 ground 없음). 폼 h1이 페이지 제목이므로 여기는 p. */}
        <aside className="hidden md:col-span-5 md:block md:pt-2">
          <p className="max-w-[16ch] text-3xl font-bold leading-snug tracking-tight">
            한국 여행을 한 화면에서 계획하고, 기록하고, 나눠요.
          </p>
          <ul className="mt-8 max-w-[34ch] space-y-3 pl-0 text-base text-body">
            {FACTS.map((fact) => (
              <li key={fact} className="flex gap-3">
                <span
                  className="mt-[0.6rem] size-1.5 shrink-0 rounded-full bg-primary"
                  aria-hidden="true"
                />
                <span>{fact}</span>
              </li>
            ))}
          </ul>
        </aside>
        <section className="md:col-span-6 md:col-start-7">
          <div className="mx-auto w-full max-w-sm">{children}</div>
        </section>
      </div>
      <PublicColophon />
    </div>
  );
}
