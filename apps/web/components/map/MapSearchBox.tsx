'use client';

import { useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { ApiError, featureApi } from '@tripmate/api-client';
import type { FeatureSummary } from '@tripmate/schemas';
import { apiClient } from '@/lib/api';

export interface MapSearchBoxProps {
  onSelect: (feature: FeatureSummary) => void;
  className?: string;
}

export function MapSearchBox({ onSelect, className }: MapSearchBoxProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<FeatureSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const term = query.trim();
    if (!term) return;
    setLoading(true);
    setError(null);
    try {
      const res = await featureApi(apiClient).search({ q: term, limit: 8 });
      setResults(res);
      if (res.length === 0) setError('검색 결과가 없습니다.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '검색에 실패했습니다.');
    } finally {
      setLoading(false);
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
        <p className="mt-1 rounded-sm bg-error-bg px-2 py-1 text-xs text-error-text">{error}</p>
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
                <span className="block truncate text-sm font-medium text-ink">{feature.title}</span>
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
