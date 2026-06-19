'use client';

import type { AnchorHTMLAttributes, ReactNode } from 'react';

export type DocumentNavLinkProps = {
  href: string;
  children: ReactNode;
} & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'>;

/**
 * `next/link` 대신 브라우저 document navigation으로 이동하는 링크 (kor-travel-geo T-278 이식).
 *
 * 평범한 `<a>`는 Next client router를 거치지 않으므로 `_rsc` payload fetch를 만들지 않는다.
 * chunk/RSC client transition 실패가 잦은 admin 좌측 메뉴 / 교차 segment 이동에서, 실패한
 * client routing이 Next 기본 오류 화면(`This page couldn’t load`)으로 새는 것을 예방한다.
 * 복구 측면은 `app/error.tsx`/`app/global-error.tsx`의 auto-reload(`lib/error-recovery`)가 맡는다.
 */
export function DocumentNavLink({ href, children, ...rest }: DocumentNavLinkProps) {
  return (
    <a href={href} {...rest}>
      {children}
    </a>
  );
}
