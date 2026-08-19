import type { ReactNode } from 'react';
import { PublicColophon, PublicMasthead } from '@/components/app/PublicChrome';

/* Hallmark · genre: modern-minimal · macrostructure: Long Document(콘텐츠) · design-system: DESIGN.md
 * nav: N1(공개 masthead) · footer: Ft2(colophon + 법무 링크)
 * 법무는 공개 표면인데 T-312가 재설계한 공개 chrome을 유일하게 쓰지 않아 문서 간 이동 링크가 0개였다.
 */
export default function LegalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <PublicMasthead />
      <main className="flex-1">{children}</main>
      <PublicColophon />
    </div>
  );
}
