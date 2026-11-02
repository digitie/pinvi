import { useEffect, useRef } from 'react';

/**
 * `key`가 바뀔 때마다 `load(key, signal)`을 부르고, 키가 바뀌거나 언마운트되면 직전 요청을
 * **취소**한다. 취소된 요청의 결과는 `onLoad`로 넘기지 않는다.
 *
 * 2026-11-02 prod 점검: 지도에서 마커를 바꿔 고를 때마다 상세·날씨 요청이 취소 없이 쌓였다.
 * 날씨 한 건이 ~31s 걸리는 동안 브라우저의 origin당 연결(HTTP/1.1 6개)을 붙잡아, 서버에서는
 * 0.1s짜리 다른 요청이 클라이언트에서 5~7s 줄을 섰다. `active` 플래그로 결과만 버리면 요청은
 * 계속 살아 있다 — 연결을 놓으려면 fetch 자체를 abort해야 한다.
 */
export function useAbortableLoad<T>(
  key: string | null,
  load: (key: string, signal: AbortSignal) => Promise<T>,
  onLoad: (value: T) => void,
): void {
  const loadRef = useRef(load);
  const onLoadRef = useRef(onLoad);
  useEffect(() => {
    loadRef.current = load;
    onLoadRef.current = onLoad;
  });

  useEffect(() => {
    if (!key) return;
    const controller = new AbortController();
    loadRef.current(key, controller.signal).then(
      (value) => {
        if (!controller.signal.aborted) onLoadRef.current(value);
      },
      () => {
        // 취소·실패는 호출부가 빈 상태로 degrade한다.
      },
    );
    return () => controller.abort();
  }, [key]);
}
