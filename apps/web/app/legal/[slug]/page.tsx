import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';
import { getLegalDoc, LEGAL_SLUGS } from '@/lib/legalDocs';

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

export default async function LegalDocPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const doc = getLegalDoc(slug);
  if (!doc) notFound();

  return (
    <main className="mx-auto max-w-3xl px-4 py-10" data-testid="legal-doc">
      <nav className="mb-6 text-sm">
        <Link href="/" className="text-primary hover:underline">
          ← Pinvi
        </Link>
      </nav>

      <h1 className="text-2xl font-bold text-ink md:text-3xl">{doc.title}</h1>
      <p className="mt-2 text-sm text-muted">
        버전 {doc.version} · 시행일 {doc.effectiveDate ?? '미정'}
      </p>

      {doc.draft && (
        <p
          role="note"
          className="mt-4 rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="legal-draft-banner"
        >
          본 문서는 <strong>변호사 검토 전 초안</strong>으로 법적 효력이 없습니다. 시행일·사업자
          정보는 출시 직전 확정·공지됩니다.
        </p>
      )}

      <p className="mt-4 text-sm text-ink">{doc.summary}</p>

      <div className="mt-8 space-y-6">
        {doc.sections.map((section) => (
          <section key={section.heading}>
            <h2 className="text-base font-semibold text-ink">{section.heading}</h2>
            {section.paragraphs.map((p, i) => (
              <p key={i} className="mt-1.5 text-sm leading-relaxed text-muted">
                {p}
              </p>
            ))}
          </section>
        ))}
      </div>
    </main>
  );
}
