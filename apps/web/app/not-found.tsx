import Link from 'next/link';
import { Compass, MapPinOff } from 'lucide-react';
import { FullPageMessage } from '@/components/feedback/FullPageMessage';

export default function NotFound() {
  return (
    <FullPageMessage
      icon={MapPinOff}
      title="페이지를 찾을 수 없습니다"
      description="주소가 바뀌었거나 삭제된 페이지일 수 있습니다. 아래에서 다시 시작해 주세요."
      data-testid="not-found-page"
    >
      <Link
        href="/"
        className="inline-flex items-center gap-2 rounded-sm bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary-active"
      >
        <Compass className="h-4 w-4" aria-hidden="true" />
        홈으로
      </Link>
      <Link
        href="/trips"
        className="rounded-sm border border-hairline px-6 py-3 text-sm font-semibold text-ink hover:bg-surface-soft"
      >
        내 여행
      </Link>
    </FullPageMessage>
  );
}
