import type { ReactNode } from 'react';

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <aside className="hidden flex-col justify-center bg-surface-soft px-12 py-16 md:flex">
        <h2 className="text-2xl font-bold text-ink">한국 여행을 함께 계획하세요</h2>
        <p className="mt-4 max-w-sm text-sm text-muted">
          Pinvi는 한국 공공 지도·축제·날씨·가격 데이터를 한곳에서 보며 여행을 짤 수 있는
          서비스입니다. (v1.0 출시 전 — Sprint 1 scaffolding)
        </p>
      </aside>
      <section className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">{children}</div>
      </section>
    </div>
  );
}
