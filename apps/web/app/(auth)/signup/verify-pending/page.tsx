import Link from 'next/link';

interface SearchParams {
  email?: string;
  dispatched?: string;
}

export default async function VerifyPendingPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const { email, dispatched } = await searchParams;
  const wasDispatched = dispatched === 'true';

  return (
    <div className="space-y-6 text-sm">
      <h1 className="text-2xl font-bold text-ink">이메일 인증 대기</h1>

      {email && <p className="text-ink">{email}로 인증 메일을 보냈습니다.</p>}

      {!wasDispatched && (
        <p className="text-error-text">
          이메일 발송이 보류되었습니다 (개발 모드). 콘솔 로그에서 verify URL을 확인해 주세요.
        </p>
      )}

      <p className="text-muted">
        메일을 받지 못하셨다면 스팸함을 확인하시고, 그래도 못 받으셨다면 1분 후 재발송을 요청해
        주세요.
      </p>

      <div className="flex gap-3">
        <Link href="/login" className="text-primary underline">
          로그인 화면으로
        </Link>
      </div>
    </div>
  );
}
