import { MapPinOff } from 'lucide-react';
import { PublicColophon, PublicMasthead } from '@/components/app/PublicChrome';
import { FullPageMessage } from '@/components/feedback/FullPageMessage';
import { ButtonLink } from '@/components/ui/Button';

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas text-ink">
      <PublicMasthead />
      <main className="flex-1">
        <FullPageMessage
          icon={MapPinOff}
          title="페이지를 찾을 수 없습니다"
          description="주소가 바뀌었거나 삭제된 페이지일 수 있습니다. 아래에서 다시 시작해 주세요."
          data-testid="not-found-page"
        >
          <ButtonLink href="/" variant="primary">
            홈으로
          </ButtonLink>
          <ButtonLink href="/trips" variant="secondary">
            내 여행
          </ButtonLink>
        </FullPageMessage>
      </main>
      <PublicColophon />
    </div>
  );
}
