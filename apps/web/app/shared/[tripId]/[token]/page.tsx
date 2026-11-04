'use client';

import { useEffect } from 'react';
import { useParams } from 'next/navigation';
import { PublicColophon, PublicMasthead } from '@/components/app/PublicChrome';
import { ButtonLink } from '@/components/ui/Button';
import { SharedTripView } from '@/components/trips/SharedTripView';
import { sharedLoginHref } from '@/lib/loginReturnTo';
import { stashSharedToken } from '@/lib/sharedTokenStash';

/* Hallmark · genre: modern-minimal · macrostructure: Long Document(읽기 전용 콘텐츠) · design-system: DESIGN.md · designed-as-app
 * nav: N1(워드마크 + 로그인/시작하기) · footer: Ft2 — 익명 방문자의 첫 접점이라 공개 chrome을 붙인다.
 */
export default function SharedTripPage() {
  const params = useParams<{ tripId: string; token: string }>();
  // 로그인 복귀 경로에는 토큰을 싣지 않는다(#671) — 같은 탭이 로그인 뒤 `/shared/{tripId}`에서 되찾는다.
  useEffect(() => stashSharedToken(params.tripId, params.token), [params.tripId, params.token]);
  return (
    <div className="flex min-h-dvh flex-col bg-canvas text-ink">
      <PublicMasthead
        actions={
          <>
            <ButtonLink href={sharedLoginHref(params.tripId)} prefetch={false} variant="ghost">
              로그인
            </ButtonLink>
            <ButtonLink href="/signup" variant="secondary">
              시작하기
            </ButtonLink>
          </>
        }
      />
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        <SharedTripView tripId={params.tripId} token={params.token} />
      </main>
      <PublicColophon />
    </div>
  );
}
