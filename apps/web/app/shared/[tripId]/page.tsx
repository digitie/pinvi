'use client';

import { useEffect, useSyncExternalStore } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { Link2Off } from 'lucide-react';
import { PublicColophon, PublicMasthead } from '@/components/app/PublicChrome';
import { FullPageMessage } from '@/components/feedback/FullPageMessage';
import { ButtonLink } from '@/components/ui/Button';
import { readStashedSharedToken } from '@/lib/sharedTokenStash';

/* Hallmark · genre: modern-minimal · macrostructure: Long Document · design-system: DESIGN.md · designed-as-app
 * 로그인 복귀 전용 경유지(#671): 복귀 경로에는 공유 토큰 대신 `/shared/{tripId}`만 싣는다.
 * 같은 탭의 sessionStorage에 토큰이 있으면 공유 화면으로 돌아가고, 없으면(새 탭 로그인 등) 안내한다.
 */
/** sessionStorage는 다른 탭의 변경을 알리지 않는다 — 처음 읽은 값으로 충분하다. */
function subscribeNothing(): () => void {
  return () => undefined;
}

export default function SharedTripResumePage() {
  const params = useParams<{ tripId: string }>();
  const router = useRouter();
  // 서버 렌더에서는 undefined(확인 중), 브라우저에서는 저장된 토큰 또는 null(없음).
  const token = useSyncExternalStore(
    subscribeNothing,
    () => readStashedSharedToken(params.tripId),
    () => undefined,
  );
  const missing = token === null;

  useEffect(() => {
    if (token) router.replace(`/shared/${encodeURIComponent(params.tripId)}/${encodeURIComponent(token)}`);
  }, [params.tripId, router, token]);

  return (
    <div className="flex min-h-dvh flex-col bg-canvas text-ink">
      <PublicMasthead />
      <main id="main" tabIndex={-1} className="flex-1">
        {missing ? (
          <FullPageMessage
            icon={Link2Off}
            title="공유 화면으로 돌아가 주세요"
            description="로그인했습니다. 공유 링크를 연 원래 탭으로 돌아가거나, 받은 공유 링크를 다시 열어 주세요."
            data-testid="shared-resume-missing"
          >
            <ButtonLink href="/trips" variant="primary">
              내 여행
            </ButtonLink>
          </FullPageMessage>
        ) : (
          <p className="px-6 py-8 text-sm text-muted" role="status">
            공유 화면으로 돌아가는 중…
          </p>
        )}
      </main>
      <PublicColophon />
    </div>
  );
}
