/** 앱·공개 화면이 공통으로 제공하는 키보드 본문 이동. */
export function SkipToContentLink() {
  return (
    <a href="#main"
      className="focus-ring sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-overlay focus:rounded-sm focus:bg-canvas focus:px-4 focus:py-3 focus:text-ink">
      본문으로 건너뛰기
    </a>
  );
}
