import type { ReactNode } from 'react';

/**
 * `(admin)` 라우트 그룹 셸 — admin 표면 스코프 표식만 담당한다(T-356).
 *
 * `data-pv-surface="admin"`은 `app/globals.css`의 admin 전용 토큰 재정의(타이포 스케일)가
 * 걸리는 지점이다. kor-travel-map admin의 7단 타이포(12/13.5/15/17/20/24/30px)를 이식하되,
 * `text-xs`/`text-sm`/`text-base` 같은 이름은 사용자 표면도 쓰기 때문에 전역에서 바꾸면
 * 랜딩·여행·지도 화면의 활자가 통째로 흔들린다. 그래서 CSS 변수를 이 subtree에서만
 * 재정의한다 — 유틸(`.text-sm { font-size: var(--text-sm) }`)은 그대로 두고 변수만 가린다.
 *
 * 왜 `admin/layout.tsx`가 아니라 여기인가: 그 파일의 `AdminGuard`는 로그인 화면·권한 확인 중·
 * 권한 없음·정상 4가지 트리를 각각 반환한다. 그중 하나에 표식을 붙이면 나머지가 누락된다.
 * 라우트 그룹 레이아웃은 네 경우 모두를 감싼다.
 *
 * `display: contents`라 레이아웃 박스를 만들지 않는다 — 기존 flex/grid 계층에 영향이 없다.
 */
export default function AdminSurfaceLayout({ children }: { children: ReactNode }) {
  return (
    <div data-pv-surface="admin" style={{ display: 'contents' }}>
      {children}
    </div>
  );
}
