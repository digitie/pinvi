import { afterEach, expect, it, vi } from 'vitest';
import { openTripPrintWindow } from '../lib/tripPrintWindow';

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});
function fixture() {
  const doc = document.implementation.createHTMLDocument();
  const popup = {
    document: doc,
    opener: window,
    closed: false,
    focus: vi.fn(),
    print: vi.fn(),
    close: vi.fn(),
  };
  vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
  const content = document.createElement('article');
  content.textContent = '<script>inert user text</script>';
  return { doc, popup, content };
}
it('공유 URL을 복사하지 않는 별도 정적 문서에서만 native print를 호출한다', async () => {
  const { doc, popup, content } = fixture();
  const original = document.createElement('style');
  original.textContent = 'body{background:url(https://example.com/?secret=hidden)}';
  document.head.append(original);
  try {
    await openTripPrintWindow(content, '여행 일정', new AbortController().signal);
    expect(popup.opener).toBeNull();
    expect(popup.print).toHaveBeenCalledOnce();
    expect(doc.head.querySelector('meta[name=referrer]')?.getAttribute('content')).toBe(
      'no-referrer',
    );
    expect(doc.body.querySelector('script,img,a')).toBeNull();
    expect(doc.documentElement.innerHTML).not.toContain('secret');
    expect(doc.documentElement.dataset.printReady).toBe('true');
  } finally {
    original.remove();
  }
});
it('font 준비가 지연되면 8초 안에 실패하고 popup을 정리한다', async () => {
  vi.useFakeTimers();
  const { doc, popup, content } = fixture();
  Object.defineProperty(doc, 'fonts', { value: { ready: new Promise(() => {}) } });
  const task = openTripPrintWindow(content, '여행', new AbortController().signal);
  const rejected = expect(task).rejects.toThrow('준비 시간이 초과');
  await vi.advanceTimersByTimeAsync(8000);
  await rejected;
  expect(popup.close).toHaveBeenCalledOnce();
  expect(popup.print).not.toHaveBeenCalled();
});
it('stylesheet는 승인된 Next static CSS 경로만 복사한다', async () => {
  const { doc, popup, content } = fixture();
  const link = document.createElement('link');
  link.rel = 'stylesheet';
  link.href = '/private?token=must-not-copy';
  document.head.append(link);
  try {
    await openTripPrintWindow(content, '여행', new AbortController().signal);
    expect(doc.querySelectorAll('link')).toHaveLength(0);
    expect(doc.documentElement.outerHTML).not.toContain('must-not-copy');
    expect(popup.print).toHaveBeenCalledOnce();
  } finally {
    link.remove();
  }
});
