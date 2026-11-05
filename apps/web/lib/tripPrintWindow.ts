/** token 없는 about:blank 인쇄 문서. 사용자 문자열은 HTML로 파싱하지 않는다. */
export async function openTripPrintWindow(
  content: HTMLElement,
  title: string,
  signal: AbortSignal,
): Promise<void> {
  const popup = window.open('about:blank', '_blank');
  if (!popup)
    throw new Error('인쇄창을 열지 못했습니다. 이 사이트의 팝업을 허용한 뒤 다시 시도하세요.');
  popup.opener = null;
  const abort = () => popup.close();
  signal.addEventListener('abort', abort, { once: true });
  let timer: ReturnType<typeof setTimeout> | undefined;
  let rejectOnAbort: (() => void) | undefined;
  try {
    if (signal.aborted) throw new DOMException('인쇄를 취소했습니다.', 'AbortError');
    const doc = popup.document;
    doc.title = title;
    const meta = doc.createElement('meta');
    meta.name = 'referrer';
    meta.content = 'no-referrer';
    doc.head.append(meta);
    const charset = doc.createElement('meta');
    charset.setAttribute('charset', 'utf-8');
    doc.head.append(charset);
    doc.documentElement.lang = 'ko';
    const sheets: Promise<void>[] = [];
    for (const original of document.head.querySelectorAll('link[rel="stylesheet"]')) {
      if (original instanceof HTMLLinkElement) {
        const url = new URL(original.href);
        // 기존 앱의 같은 origin CSS만 복사한다. 외부 stylesheet로 공유 URL을 전달하지 않는다.
        if (
          url.origin !== window.location.origin ||
          !url.pathname.startsWith('/_next/static/') ||
          !url.pathname.endsWith('.css')
        )
          continue;
        url.search = '';
        url.hash = '';
        const link = doc.createElement('link');
        link.rel = 'stylesheet';
        link.href = url.href;
        link.referrerPolicy = 'no-referrer';
        sheets.push(
          new Promise<void>((resolve, reject) => {
            link.onload = () => resolve();
            link.onerror = () =>
              reject(new Error('인쇄 스타일을 불러오지 못했습니다. 잠시 후 다시 시도하세요.'));
          }),
        );
        doc.head.append(link);
      } else {
        doc.head.append(original.cloneNode(true));
      }
    }
    const style = doc.createElement('style');
    style.textContent =
      'html,body{height:auto!important;overflow:visible!important;background:white!important;margin:0}body{padding:18px} @media print{body{padding:0}}';
    doc.head.append(style);
    doc.body.style.fontFamily = getComputedStyle(content).fontFamily;
    doc.body.append(content.cloneNode(true));
    const ready = (async () => {
      await Promise.all(sheets);
      await doc.fonts?.ready;
    })();
    await Promise.race([
      ready,
      new Promise<never>((_, reject) => {
        timer = setTimeout(
          () => reject(new Error('인쇄 글꼴 준비 시간이 초과됐습니다. 다시 시도하세요.')),
          8000,
        );
        rejectOnAbort = () => reject(new DOMException('인쇄를 취소했습니다.', 'AbortError'));
        signal.addEventListener('abort', rejectOnAbort, { once: true });
      }),
    ]);
    if (signal.aborted || popup.closed)
      throw new DOMException('인쇄를 취소했습니다.', 'AbortError');
    doc.documentElement.dataset.printReady = 'true';
    popup.focus();
    popup.print();
  } catch (error) {
    popup.close();
    throw error;
  } finally {
    if (timer) clearTimeout(timer);
    signal.removeEventListener('abort', abort);
    if (rejectOnAbort) signal.removeEventListener('abort', rejectOnAbort);
  }
}
