import { useEffect, useState } from 'react';

/** 값을 delay 후에 갱신 — 검색 / viewport fetch 디바운스에 사용. */
export function useDebounce<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
