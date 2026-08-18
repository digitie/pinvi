import { ResendVerificationButton } from '@/components/forms/ResendVerificationButton';
import { ButtonLink } from '@/components/ui/Button';

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
  const isDev = process.env.NODE_ENV !== 'production';

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight text-ink">메일함을 확인해 주세요</h1>
        <p className="text-base text-body">
          {email ? (
            <>
              <span className="font-semibold text-ink [overflow-wrap:anywhere]">{email}</span>로
              인증 메일을 보냈습니다. 메일의 링크를 열면 가입이 끝납니다.
            </>
          ) : (
            '가입하신 이메일로 인증 메일을 보냈습니다. 메일의 링크를 열면 가입이 끝납니다.'
          )}
        </p>
      </div>

      {!wasDispatched ? (
        <p className="rounded-sm bg-surface-soft px-3 py-2 text-sm text-body" role="status">
          {isDev
            ? '이메일 발송이 보류되었습니다(개발 모드). API 콘솔 로그의 verify URL로 인증할 수 있습니다.'
            : email
              ? '인증 메일 발송이 지연되고 있습니다. 잠시 뒤 아래에서 다시 보내 주세요.'
              : '인증 메일 발송이 지연되고 있습니다. 로그인 화면에서 다시 요청할 수 있습니다.'}
        </p>
      ) : null}

      <p className="text-sm text-muted">
        메일이 보이지 않으면 스팸함을 확인해 주세요. 그래도 없으면 다시 보낼 수 있습니다(1분에 한
        번).
      </p>

      {email ? <ResendVerificationButton email={email} /> : null}

      <ButtonLink href="/login" variant="ghost" fullWidth>
        로그인 화면으로
      </ButtonLink>
    </div>
  );
}
