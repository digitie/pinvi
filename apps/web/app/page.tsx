import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 px-4 py-16 text-center">
      <h1 className="text-3xl font-bold text-ink">TripMate</h1>
      <p className="max-w-md text-sm text-muted">
        한국 여행 계획·기록·공유 (v2). 회원가입 / 로그인 / 여행 shell / 추천 여행 shell이
        Sprint 4 기준으로 동작합니다.
      </p>
      <div className="flex gap-3">
        <Link
          href="/login"
          className="rounded-sm bg-primary px-6 py-3 text-sm font-semibold text-white hover:bg-primary-active"
        >
          로그인
        </Link>
        <Link
          href="/signup"
          className="rounded-sm border border-hairline px-6 py-3 text-sm font-semibold text-ink hover:bg-surface-soft"
        >
          회원가입
        </Link>
        <Link
          href="/trips"
          className="rounded-sm border border-hairline px-6 py-3 text-sm font-semibold text-ink hover:bg-surface-soft"
        >
          여행
        </Link>
      </div>
    </main>
  );
}
