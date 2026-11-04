'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Bookmark, ExternalLink, Loader2, MapPin, Search } from 'lucide-react';
import { ApiError, geoApi } from '@pinvi/api-client';
import type { PlaceSearchResult } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';

export interface MapSearchBoxProps {
  onSelect: (result: PlaceSearchResult) => void;
  /** 좌표 없는 feature를 상세로 여는 호출부만 허용한다. 여행 POI 추가에는 좌표가 필요하다. */
  allowFeatureDetail?: boolean;
  className?: string;
  /**
   * 검색 시점의 지역 편향 bbox(`lng_min,lat_min,lng_max,lat_max`)를 돌려준다 — 여행 장소 범위 또는
   * 지금 지도 화면. 그 범위 안의 장소가 먼저 나온다(밖의 결과도 뒤에 남는다). 없으면 null.
   */
  getBias?: () => string | null;
}

type Source = PlaceSearchResult['source'];

const MIN_CHARS = 2;
const DEBOUNCE_MS = 250;

// source별 표시 배지 — kakao/naver는 약관상 가시적 attribution이 필수(ADR-054 M19).
const SOURCE_META: Record<Source, { label: string; badgeClass: string; icon: 'pin' | 'bookmark' }> =
  {
    feature: { label: '장소', badgeClass: 'bg-surface-soft text-muted', icon: 'pin' },
    my_poi: { label: '내 여행', badgeClass: 'bg-surface-strong text-ink', icon: 'bookmark' },
    address: { label: '주소', badgeClass: 'bg-surface-soft text-muted', icon: 'pin' },
    kakao: { label: '카카오', badgeClass: 'bg-marker-p-03/20 text-ink', icon: 'pin' },
    naver: { label: '네이버 검색', badgeClass: 'bg-marker-p-05/15 text-ink', icon: 'pin' },
  };

/**
 * 결과 둘째 줄의 분류 이름. feature의 `category`는 Map 코드(`02010100`)라 사람에게 보이지 않고
 * 서버가 채운 `category_label`(잎 이름)만 쓴다. 외부(kakao/naver) 결과의 `category`는 provider가
 * 준 이름이라 그대로 쓴다(2026-11-02 prod e2e — 검색 결과가 숫자 코드만 보였다).
 */
export function searchResultCategory(result: PlaceSearchResult): string | null {
  if (result.category_label) return result.category_label;
  return result.source === 'feature' ? null : (result.category ?? null);
}

function resultKey(r: PlaceSearchResult, index: number): string {
  return `${r.source}-${r.feature_id ?? r.poi_id ?? r.external_id ?? index}`;
}

export function MapSearchBox({
  onSelect,
  allowFeatureDetail = false,
  className,
  getBias,
}: MapSearchBoxProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlaceSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const searchAbort = useRef<AbortController | null>(null);
  // 최신 편향 함수를 검색 시점에 읽는다(runSearch는 안정 참조라 prop을 직접 닫으면 낡는다).
  const getBiasRef = useRef(getBias);
  useEffect(() => {
    getBiasRef.current = getBias;
  }, [getBias]);

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
        { q: term, limit: 8, bbox: getBiasRef.current?.() ?? null },
        { signal: controller.signal },
      );
      if (controller.signal.aborted || searchAbort.current !== controller) return;
      setResults(res.results);
      if (res.results.length === 0) setError('검색 결과가 없습니다.');
    } catch (err) {
      if (isAbortError(err) || searchAbort.current !== controller) return;
      setError(err instanceof ApiError ? err.message : '검색에 실패했습니다.');
    } finally {
      if (searchAbort.current === controller) setLoading(false);
    }
  }, []);

  // 검색어가 바뀌면 이전 결과를 즉시 지워 새 debounce 구간에서 다른 장소를 고르지 않게 한다.
  // 결과/에러/로딩을 렌더 중에
  // 리셋한다(react-hooks/set-state-in-effect: effect 안 동기 setState 금지 — 공식
  // "Adjusting state when a prop changes" 패턴). 디바운스 타이머 예약과 abort는 side effect라
  // 아래 effect에 그대로 둔다.
  const term = query.trim();
  const [prevTerm, setPrevTerm] = useState(term);
  if (term !== prevTerm) {
    setPrevTerm(term);
    setResults([]);
    setError(null);
    setLoading(false);
  }

  // 디바운스 자동완성(F3) — 2자 이상 입력 시 250ms 뒤 검색. 입력마다 재요청/직전 요청은 취소.
  // 트림 값이 아니라 원본 `query`를 dep으로 둬야 공백만 바뀌어도 디바운스가 그대로 재시작된다
  // (기존 동작 유지).
  useEffect(() => {
    if (term.length < MIN_CHARS) {
      searchAbort.current?.abort();
      return;
    }
    const timer = setTimeout(() => void runSearch(term), DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      searchAbort.current?.abort();
    };
  }, [query, term, runSearch]);

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
      {/* data-map-fit-anchor: 여행 지도 맞춤 여백은 이 입력 줄 아래까지만 피한다(결과 목록 제외). */}
      <form
        onSubmit={submit}
        className="flex items-center gap-1.5 rounded-sm border border-hairline bg-canvas px-2 shadow-card"
        data-map-fit-anchor=""
      >
        <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="장소·주소 검색"
          aria-label="장소·주소 검색"
          className="min-h-11 w-full bg-transparent text-sm text-ink outline-hidden"
        />
        {loading && (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted" aria-hidden="true" />
        )}
      </form>
      {error && (
        <p role="alert" className="mt-1 rounded-sm bg-error-bg px-2 py-1 text-xs text-error-text">
          {error}
        </p>
      )}
      {results.length > 0 && (
        <ul className="mt-1 max-h-64 overflow-auto rounded-sm border border-hairline bg-canvas shadow-card">
          {results.map((result, index) => {
            const meta = SOURCE_META[result.source];
            const secondary =
              result.road_address ?? result.address ?? searchResultCategory(result) ?? null;
            const isExternal = result.source === 'kakao' || result.source === 'naver';
            // §5.2(HARD): kakao/naver 행은 가시적 attribution 배지 + provider_url back-link 필수.
            // 앵커를 pick 버튼 안에 중첩하면 invalid HTML이므로 형제 요소로 둔다.
            const backLink = isExternal && result.provider_url ? result.provider_url : null;
            const canOpenDetail = allowFeatureDetail && !!result.feature_id;
            return (
              <li key={resultKey(result, index)} className="flex items-stretch">
                <button
                  type="button"
                  disabled={!result.coord && !canOpenDetail}
                  onClick={() => handlePick(result)}
                  className="flex min-w-0 flex-1 items-start gap-2 px-3 py-2 text-left hover:bg-surface-soft disabled:cursor-default disabled:opacity-60"
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
                        className={`shrink-0 rounded-sm px-1 py-0.5 text-xs font-semibold ${meta.badgeClass}`}
                      >
                        {meta.label}
                      </span>
                    </span>
                    {!result.coord && (
                      <span className="block text-xs text-muted">
                        {canOpenDetail ? '상세 보기' : '위치 정보 없음'}
                      </span>
                    )}
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
