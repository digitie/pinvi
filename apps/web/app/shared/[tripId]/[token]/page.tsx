'use client';

import { useParams } from 'next/navigation';
import { PublicColophon, PublicMasthead } from '@/components/app/PublicChrome';
import { ButtonLink } from '@/components/ui/Button';
import { SharedTripView } from '@/components/trips/SharedTripView';

/* Hallmark · genre: modern-minimal · macrostructure: Workbench(읽기 전용) · design-system: DESIGN.md · designed-as-app
 * nav: N1(워드마크 + 로그인/시작하기) · footer: Ft2 — 익명 방문자의 첫 접점이라 공개 chrome을 붙인다.
 */
export default function SharedTripPage() {
  const params = useParams<{ tripId: string; token: string }>();
  return (
    <div className="flex min-h-dvh flex-col bg-canvas text-ink">
      <PublicMasthead
        actions={
          <>
            <ButtonLink href="/login" variant="ghost" size="sm">
              로그인
            </ButtonLink>
            <ButtonLink href="/signup" variant="primary" size="sm">
              시작하기
            </ButtonLink>
          </>
        }
      />
      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <SharedTripView tripId={params.tripId} token={params.token} />
      </main>
      <PublicColophon />
    </div>
  );
}
