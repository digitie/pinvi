import Link from 'next/link';
import { CalendarDays, LogIn, Sparkles, type LucideIcon } from 'lucide-react';

const actions: {
  href: string;
  title: string;
  description: string;
  icon: LucideIcon;
  primary?: boolean;
}[] = [
  {
    href: '/login',
    title: '로그인',
    description: '내 여행 계획과 공유 링크를 이어서 관리합니다.',
    icon: LogIn,
    primary: true,
  },
  {
    href: '/signup',
    title: '회원가입',
    description: '약관 동의와 이메일 인증으로 Pinvi 계정을 만듭니다.',
    icon: Sparkles,
  },
  {
    href: '/trips',
    title: '여행',
    description: '일정, POI, 추천 여행 shell로 바로 이동합니다.',
    icon: CalendarDays,
  },
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-canvas px-6 py-12 text-ink">
      <section className="mx-auto flex min-h-[calc(100vh-6rem)] w-full max-w-5xl flex-col justify-center space-y-6">
        <div className="rounded-md border border-hairline bg-canvas p-6 shadow-card">
          <div className="space-y-3">
            <span className="inline-flex min-h-11 items-center rounded-full bg-surface-soft px-4 text-[13px] font-medium text-muted">
              Sprint 4 릴리즈 게이트 충족
            </span>
            <div className="space-y-2">
              <h1 className="text-[24px] font-bold leading-snug text-ink">Pinvi</h1>
              <p className="max-w-2xl text-[14px] leading-normal text-body">
                한국 여행 계획·기록·공유 앱입니다. 지도, 일정, 추천 여행, 공유 흐름을 같은 제품
                표면에서 관리합니다.
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {actions.map((action) => {
            const Icon = action.icon;
            return (
              <Link
                key={action.href}
                href={action.href}
                className="focus-ring group flex min-h-[156px] flex-col justify-between rounded-md border border-hairline bg-canvas p-6 shadow-card transition duration-normal ease-pinvi hover:-translate-y-0.5"
              >
                <span
                  className={`flex size-11 items-center justify-center rounded-full ${
                    action.primary ? 'bg-primary text-on-primary' : 'bg-surface-strong text-ink'
                  }`}
                >
                  <Icon className="size-5" aria-hidden="true" />
                </span>
                <span className="space-y-1.5">
                  <span className="block text-[18px] font-bold leading-snug text-ink">
                    {action.title}
                  </span>
                  <span className="block text-[13px] leading-normal text-muted">
                    {action.description}
                  </span>
                </span>
              </Link>
            );
          })}
        </div>
      </section>
    </main>
  );
}
