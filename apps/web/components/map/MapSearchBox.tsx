'use client';

import { useRef, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { ApiError, geoApi } from '@pinvi/api-client';
import type { FeatureSummary, PlaceSearchResult } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';

export interface MapSearchBoxProps {
  onSelect: (feature: FeatureSummary) => void;
  className?: string;
}

// T-302 bridge: 통합 `GET /search`의 feature-source 행을 기존 onSelect(FeatureSummary) 계약으로
// 매핑한다. address/kakao/naver source 행 + source 아이콘/attribution UI는 T-309a에서 재작성한다.
function featureResultToSummary(r: PlaceSearchResult): FeatureSummary | null {
  if (r.feature_id == null) return null;
  return {
    feature_id: r.feature_id,
    kind: 'place',
    name: r.name,
    coord: r.coord,
    category: r.category,
    marker_color: r.marker_color ?? 'P-13',
    marker_icon: r.marker_icon ?? 'marker',
  };
}

export function MapSearchBox({ onSelect, className }: MapSearchBoxProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<FeatureSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchAbort = useRef<AbortController | null>(null);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const term = query.trim();
    if (!term) return;
    // 직전 검색을 취소하고(서버 작업·커넥션 낭비 방지), 이 controller가 최신일 때만
    // 상태를 반영한다 (kor-travel-concierge #111 — abort 미전파 패턴 예방).
    searchAbort.current?.abort();
    const controller = new AbortController();
    searchAbort.current = controller;
    setLoading(true);
    setError(null);
    try {
      const res = await geoApi(apiClient).searchPlaces(
        { q: term, limit: 8 },
        { signal: controller.signal },
      );
      if (searchAbort.current !== controller) return;
      const features = res.results
        .map(featureResultToSummary)
        .filter((f): f is FeatureSummary => f !== null);
      setResults(features);
      if (features.length === 0) setError('검색 결과가 없습니다.');
    } catch (err) {
      if (isAbortError(err) || searchAbort.current !== controller) return;
      setError(err instanceof ApiError ? err.message : '검색에 실패했습니다.');
    } finally {
      if (searchAbort.current === controller) setLoading(false);
    }
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
          placeholder="장소 검색"
          aria-label="장소 검색"
          className="h-9 w-full bg-transparent text-sm text-ink outline-none"
        />
        {loading && <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted" aria-hidden="true" />}
      </form>
      {error && (
        <p role="alert" className="mt-1 rounded-sm bg-error-bg px-2 py-1 text-xs text-error-text">{error}</p>
      )}
      {results.length > 0 && (
        <ul className="mt-1 max-h-64 overflow-auto rounded-sm border border-hairline bg-white shadow-sm">
          {results.map((feature) => (
            <li key={feature.feature_id}>
              <button
                type="button"
                onClick={() => {
                  onSelect(feature);
                  setResults([]);
                }}
                className="block w-full px-3 py-2 text-left hover:bg-surface-soft"
              >
                <span className="block truncate text-sm font-medium text-ink">{feature.name}</span>
                {feature.category && (
                  <span className="block truncate text-xs text-muted">{feature.category}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
