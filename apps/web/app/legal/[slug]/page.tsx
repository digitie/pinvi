import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import { getLegalDoc, LEGAL_SLUGS } from '@/lib/legalDocs';

/* Hallmark · genre: modern-minimal · macrostructure: Long Document(콘텐츠) · design-system: DESIGN.md
 * measure 65ch · 좌정렬 문단 · 카드/그림자 없음 · chrome은 app/legal/layout.tsx의 N1 masthead + Ft2 colophon
 */

export function generateStaticParams(): { slug: string }[] {
  return LEGAL_SLUGS.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string }>;
}): Promise<Metadata> {
  const { slug } = await params;
  const doc = getLegalDoc(slug);
  if (!doc) return { title: 'Pinvi' };
  return { title: `${doc.title} | Pinvi`, description: doc.summary };
}

export default async function LegalDocPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const doc = getLegalDoc(slug);
  if (!doc) notFound();

  return (
    <article className="mx-auto max-w-[65ch] px-6 py-10" data-testid="legal-doc">
      <h1 className="text-2xl font-bold text-ink md:text-3xl">{doc.title}</h1>
      <p className="mt-2 text-sm text-muted">
        버전 {doc.version} · 시행일 {doc.effectiveDate ?? '미정'}
      </p>

      {doc.draft && (
        // 초안 고지는 실패가 아니라 문서 메타데이터다 — error 팔레트를 상시 점유하면
        // 진짜 오류의 신호가 죽는다(styleseed §2). 강조는 색이 아니라 굵기로.
        <p
          role="note"
          aria-label="문서 상태"
          className="mt-4 border-l-2 border-hairline bg-surface-soft px-4 py-3 text-sm text-body"
          data-testid="legal-draft-banner"
        >
          본 문서는 <strong className="font-semibold text-ink">변호사 검토 전 초안</strong>으로 법적
          효력이 없습니다. 시행일·사업자 정보는 출시 직전 확정·공지됩니다.
        </p>
      )}

      <p className="mt-4 text-base text-ink">{doc.summary}</p>

      <div className="mt-8 space-y-6">
        {doc.sections.map((section) => (
          <section key={section.heading}>
            <h2 className="text-lg font-semibold text-ink">{section.heading}</h2>
            {section.paragraphs.map((p, i) => (
              <p key={i} className="mt-2 text-base leading-relaxed text-body">
                {p}
              </p>
            ))}
          </section>
        ))}
      </div>
    </article>
  );
}
