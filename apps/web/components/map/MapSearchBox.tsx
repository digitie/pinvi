'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Bookmark, ExternalLink, Loader2, MapPin, Search } from 'lucide-react';
import { ApiError, geoApi } from '@pinvi/api-client';
import type { PlaceSearchResult } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';

export interface MapSearchBoxProps {
  onSelect: (result: PlaceSearchResult) => void;
  className?: string;
}

type Source = PlaceSearchResult['source'];

const MIN_CHARS = 2;
const DEBOUNCE_MS = 250;

// source별 표시 배지 — kakao/naver는 약관상 가시적 attribution이 필수(ADR-054 M19).
const SOURCE_META: Record<Source, { label: string; badgeClass: string; icon: 'pin' | 'bookmark' }> = {
  feature: { label: '장소', badgeClass: 'bg-surface-soft text-muted', icon: 'pin' },
  my_poi: { label: '내 여행', badgeClass: 'bg-primary/10 text-primary', icon: 'bookmark' },
  address: { label: '주소', badgeClass: 'bg-surface-soft text-muted', icon: 'pin' },
  kakao: { label: '카카오', badgeClass: 'bg-marker-p-03/20 text-ink', icon: 'pin' },
  naver: { label: '네이버 검색', badgeClass: 'bg-marker-p-05/15 text-ink', icon: 'pin' },
};

function resultKey(r: PlaceSearchResult, index: number): string {
  return `${r.source}-${r.feature_id ?? r.poi_id ?? r.external_id ?? index}`;
}

export function MapSearchBox({ onSelect, className }: MapSearchBoxProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlaceSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchAbort = useRef<AbortController | null>(null);

  const runSearch = useCallback(async (term: string) => {
    // 직전 검색을 취소하고(서버 작업·커넥션 낭비 방지), 이 controller가 최신일 때만 상태 반영.
    searchAbort.current?.abort();
    const controller = new AbortController();
    searchAbort.current = controller;
    setLoading(true);
    setError(null);
    try {
      // 서버가 internal(feature/address/my_poi) → kakao → naver 순으로 정렬해 준다(순서 유지).
      const res = await geoApi(apiClient).searchPlaces(
        { q: term, limit: 8 },
        { signal: controller.signal },
      );
      if (searchAbort.current !== controller) return;
      setResults(res.results);
      if (res.results.length === 0) setError('검색 결과가 없습니다.');
    } catch (err) {
      if (isAbortError(err) || searchAbort.current !== controller) return;
      setError(err instanceof ApiError ? err.message : '검색에 실패했습니다.');
    } finally {
      if (searchAbort.current === controller) setLoading(false);
    }
  }, []);

  // 디바운스 자동완성(F3) — 2자 이상 입력 시 250ms 뒤 검색. 입력마다 재요청/직전 요청은 취소.
  useEffect(() => {
    const term = query.trim();
    if (term.length < MIN_CHARS) {
      searchAbort.current?.abort();
      setResults([]);
      setError(null);
      setLoading(false);
      return;
    }
    const timer = setTimeout(() => void runSearch(term), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, runSearch]);

  const submit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const term = query.trim();
    // Enter는 디바운스를 건너뛰고 즉시 검색.
    if (term.length >= MIN_CHARS) void runSearch(term);
  };

  const handlePick = (result: PlaceSearchResult) => {
    onSelect(result);
    setResults([]);
    setQuery('');
  };

  return (
    <div className={className} data-testid="map-search">
      <form
        onSubmit={submit}
        className="flex items-center gap-1.5 rounded-sm border border-hairline bg-white px-2 shadow-sm"
      >
        <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="장소·주소 검색"
          aria-label="장소·주소 검색"
          className="h-9 w-full bg-transparent text-sm text-ink outline-none"
        />
        {loading && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted" aria-hidden="true" />}
      </form>
      {error && (
        <p role="alert" className="mt-1 rounded-sm bg-error-bg px-2 py-1 text-xs text-error-text">{error}</p>
      )}
      {results.length > 0 && (
        <ul className="mt-1 max-h-64 overflow-auto rounded-sm border border-hairline bg-white shadow-sm">
          {results.map((result, index) => {
            const meta = SOURCE_META[result.source];
            const secondary = result.road_address ?? result.address ?? result.category ?? null;
            const isExternal = result.source === 'kakao' || result.source === 'naver';
            // §5.2(HARD): kakao/naver 행은 가시적 attribution 배지 + provider_url back-link 필수.
            // 앵커를 pick 버튼 안에 중첩하면 invalid HTML이므로 형제 요소로 둔다.
            const backLink = isExternal && result.provider_url ? result.provider_url : null;
            return (
              <li key={resultKey(result, index)} className="flex items-stretch">
                <button
                  type="button"
                  onClick={() => handlePick(result)}
                  className="flex min-w-0 flex-1 items-start gap-2 px-3 py-2 text-left hover:bg-surface-soft"
                  data-testid={`map-search-result-${result.source}`}
                >
                  {meta.icon === 'bookmark' ? (
                    <Bookmark className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
                  ) : (
                    <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                  )}
                  <span className="min-w-0 flex-1">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span className="truncate text-sm font-medium text-ink">{result.name}</span>
                      <span
                        className={`shrink-0 rounded-sm px-1 py-0.5 text-[10px] font-semibold ${meta.badgeClass}`}
                      >
                        {meta.label}
                      </span>
                    </span>
                    {secondary && (
                      <span className="block truncate text-xs text-muted">{secondary}</span>
                    )}
                  </span>
                </button>
                {backLink && (
                  <a
                    href={backLink}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(event) => event.stopPropagation()}
                    className="flex shrink-0 items-center px-2 text-muted hover:text-ink"
                    aria-label={`${meta.label}에서 열기`}
                    data-testid={`map-search-backlink-${result.source}`}
                  >
                    <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
