import { PublicColophon, PublicMasthead } from '@/components/app/PublicChrome';
import { ButtonLink } from '@/components/ui/Button';

/* Hallmark · genre: modern-minimal · macrostructure: Narrative Workflow · design-system: DESIGN.md · designed-as-app
 * hero: H2 split diptych(7/5, 텍스트 + 단계 색인) · features: F4 step sequence(1.0→2.0→3.0) · cta: 하단 단일
 * nav: N1(워드마크 + 2 링크) · footer: Ft2(1줄 colophon) · enrichment: Tier-B 손그림 SVG(단계별 소형 도해)
 * removed: 뷰포트 중앙 hero 카드 + 동일 아이콘 카드 3장(AI 템플릿), "Sprint 4 릴리즈 게이트" 배지(내부 문구)
 */

type Stage = {
  id: string;
  number: string;
  label: string;
  heading: string;
  body: string;
  facts: string[];
  figure: 'plan' | 'record' | 'share';
};

// 사실만 쓴다 — 저장소에 구현된 기능(지도·검색·일자·공휴일·일출/일몰·날씨·첨부·공유 링크·동행자·Telegram).
const STAGES: Stage[] = [
  {
    id: 'plan',
    number: '1.0',
    label: '계획',
    heading: '지도에서 장소를 고르고 일자에 담아요.',
    body: '한국 공공 지도 위에서 바로 검색하고, 마음에 드는 장소를 여행 일자에 넣습니다. 처음 짜기 어려우면 추천 여행을 내 여행으로 복사해 고쳐 써도 됩니다.',
    facts: [
      '국내 지도(VWorld) + 카카오·네이버 장소 검색',
      '일자별 담기, 순서 바꾸기, 일자 색',
      '추천 여행을 내 여행으로 복사',
    ],
    figure: 'plan',
  },
  {
    id: 'record',
    number: '2.0',
    label: '기록',
    heading: '하루 단위로 메모·예산·시간을 남겨요.',
    body: '장소마다 메모와 예산을 적고, 사진·문서를 붙입니다. 날짜가 정해지면 공휴일과 일출·일몰, 날씨가 일정 옆에 함께 보입니다.',
    facts: [
      '장소별 메모·예산·계획 시각',
      '공휴일 · 일출/일몰 · 날씨 표시',
      '파일 첨부(여행·일자·장소 단위)',
    ],
    figure: 'record',
  },
  {
    id: 'share',
    number: '3.0',
    label: '공유',
    heading: '읽기 전용 링크로 함께 봐요.',
    body: '로그인 없이 열리는 공유 링크를 만들고, 필요 없어지면 해제합니다. 동행자를 초대해 같은 여행을 함께 편집할 수도 있습니다.',
    facts: [
      '만료·해제 가능한 읽기 전용 링크',
      '동행자 초대와 편집 권한',
      'Telegram 알림 연결(선택)',
    ],
    figure: 'share',
  },
];

/** 단계별 소형 도해 — Tier-B 손그림 SVG. 색은 토큰만(hairline/ink/primary), 장식이 아니라 단계의 형태를 요약. */
function StageFigure({ kind }: { kind: Stage['figure'] }) {
  const common = {
    viewBox: '0 0 160 100',
    className: 'h-auto w-full max-w-[16rem]',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.5,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: 'false' as const,
  };
  if (kind === 'plan') {
    return (
      <svg {...common} className={`${common.className} text-hairline`}>
        <path d="M8 24h144M8 52h144M8 80h144M40 8v84M92 8v84M132 8v84" />
        <g className="text-ink">
          <path d="M60 60c-7-7-11-12-11-19a11 11 0 0 1 22 0c0 7-4 12-11 19Z" />
          <circle cx="60" cy="41" r="2.5" fill="currentColor" stroke="none" />
          <path d="M112 44c-6-6-9-10-9-16a9 9 0 0 1 18 0c0 6-3 10-9 16Z" />
          <circle cx="112" cy="28" r="2" fill="currentColor" stroke="none" />
        </g>
        <path d="M60 60 96 78" strokeDasharray="3 4" className="text-ink" />
        <circle cx="96" cy="78" r="4" className="text-primary" fill="currentColor" stroke="none" />
      </svg>
    );
  }
  if (kind === 'record') {
    return (
      <svg {...common} className={`${common.className} text-hairline`}>
        <rect x="8" y="10" width="144" height="80" rx="6" />
        <path d="M8 34h144M8 58h144" />
        <g className="text-ink">
          <path d="M20 22h34M20 46h48M20 70h28" strokeWidth={2.5} />
          <path d="M120 22h20M120 46h20M120 70h20" />
        </g>
        <rect
          x="14"
          y="17"
          width="4"
          height="10"
          rx="1"
          className="text-primary"
          fill="currentColor"
          stroke="none"
        />
      </svg>
    );
  }
  return (
    <svg {...common} className={`${common.className} text-hairline`}>
      <rect x="8" y="34" width="72" height="32" rx="16" />
      <rect x="104" y="34" width="48" height="32" rx="16" />
      <path d="M80 50h24" strokeDasharray="3 4" className="text-ink" />
      <g className="text-ink">
        <path d="M30 50h34" strokeWidth={2.5} />
        <path d="M118 50h20" strokeWidth={2.5} />
      </g>
      <circle cx="30" cy="50" r="4" className="text-primary" fill="currentColor" stroke="none" />
    </svg>
  );
}

export default function HomePage() {
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

      <main id="main" className="flex-1">
        {/* Hero — H2 split diptych 7/5. 왼쪽 문장·CTA, 오른쪽은 이미지 대신 단계 색인(페이지 내 링크). */}
        <section
          className="mx-auto grid w-full max-w-6xl gap-10 px-6 pb-16 pt-14 md:grid-cols-12 md:gap-8 md:pb-24 md:pt-24"
          data-testid="home-hero"
        >
          <div className="md:col-span-7">
            <h1 className="max-w-[18ch] text-4xl font-bold leading-[1.15] tracking-tight md:text-5xl">
              지도에서 고르고, 하루씩 담고, 링크로 나눠요.
            </h1>
            <p className="mt-6 max-w-[38ch] text-lg leading-relaxed text-body">
              Pinvi는 한국 공공 지도·날씨·행사 데이터를 한 화면에서 보며 여행 일정을 짜고, 기록하고,
              읽기 전용 링크로 공유하는 서비스입니다.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <ButtonLink href="/signup" variant="primary" size="lg">
                무료로 시작하기
              </ButtonLink>
              <ButtonLink href="/login" variant="secondary" size="lg">
                로그인
              </ButtonLink>
            </div>
          </div>

          <nav
            aria-label="사용 흐름"
            className="self-end border-t border-ink pt-4 md:col-span-4 md:col-start-9"
          >
            <ol className="m-0 list-none space-y-1 p-0">
              {STAGES.map((stage) => (
                <li key={stage.id}>
                  <a
                    href={`#${stage.id}`}
                    className="focus-ring flex min-h-11 items-baseline gap-4 rounded-sm text-ink hover:text-cta"
                  >
                    <span className="w-9 shrink-0 font-mono text-sm tabular-nums text-muted">
                      {stage.number}
                    </span>
                    <span className="text-lg font-semibold">{stage.label}</span>
                    <span className="ml-auto text-sm text-muted" aria-hidden="true">
                      ↓
                    </span>
                  </a>
                </li>
              ))}
            </ol>
          </nav>
        </section>

        {/* F4 step sequence — 단계 사이는 두꺼운 번호 rule, 각 단계는 [번호 | 본문 | 도해]. */}
        <ol className="m-0 list-none p-0" aria-label="Pinvi 사용 단계">
          {STAGES.map((stage, index) => (
            <li
              key={stage.id}
              id={stage.id}
              className={`border-t-2 border-ink scroll-mt-16 ${index === STAGES.length - 1 ? 'border-b-2' : ''}`}
            >
              <article className="mx-auto grid w-full max-w-6xl gap-6 px-6 py-12 md:grid-cols-12 md:gap-8 md:py-16">
                <p className="m-0 font-mono text-sm tabular-nums text-muted md:col-span-2">
                  {stage.number} · {stage.label}
                </p>
                <div className="md:col-span-6">
                  <h2 className="text-2xl font-bold leading-snug tracking-tight md:text-3xl">
                    {stage.heading}
                  </h2>
                  <p className="mt-4 max-w-[46ch] text-base leading-relaxed text-body">
                    {stage.body}
                  </p>
                  <ul className="mt-5 max-w-[46ch] space-y-2 pl-0 text-sm text-ink">
                    {stage.facts.map((fact) => (
                      <li key={fact} className="flex gap-3">
                        <span
                          className="mt-[0.55rem] size-1.5 shrink-0 rounded-full bg-ink"
                          aria-hidden="true"
                        />
                        <span>{fact}</span>
                      </li>
                    ))}
                  </ul>
                </div>
                <figure className="m-0 md:col-span-4 md:justify-self-end">
                  <StageFigure kind={stage.figure} />
                </figure>
              </article>
            </li>
          ))}
        </ol>

        {/* 하단 단일 CTA — Narrative Workflow "Start at stage 1 →". */}
        <section className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-6 py-14 sm:flex-row sm:items-center sm:justify-between md:py-20">
          <p className="m-0 text-xl font-semibold tracking-tight">
            1.0 계획부터 시작해 볼까요? 이메일 인증만 하면 바로 여행을 만들 수 있어요.
          </p>
          <ButtonLink href="/signup" variant="primary" size="lg" className="shrink-0">
            1.0부터 시작하기
          </ButtonLink>
        </section>
      </main>

      <PublicColophon />
    </div>
  );
}
