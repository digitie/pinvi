import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { poiApi } from '@pinvi/api-client';
import type { PoiPlaceDetails } from '@pinvi/schemas';
import { apiClient } from './api';

const detailsKey = (tripId: string, poiId: string) => ['poi', 'place-details', tripId, poiId];

/**
 * 여행 장소에 저장된 영업 정보(`GET …/place-details`). 시트를 열 때만 부른다. "다시 읽어오기"
 * (`POST …/place-details/refresh`)는 성공하면 값을 바꾸고, 실패해도 기존 값을 둔다(웹 `usePlaceDetails`와 같다).
 */
export function usePlaceDetails(tripId: string, poiId: string) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: detailsKey(tripId, poiId),
    queryFn: ({ signal }) => poiApi(apiClient).placeDetails(tripId, poiId, { signal }),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const refresh = useMutation({
    mutationFn: () => poiApi(apiClient).refreshPlaceDetails(tripId, poiId),
    onSuccess: (data: PoiPlaceDetails) => queryClient.setQueryData(detailsKey(tripId, poiId), data),
  });
  return { query, refresh };
}

/**
 * 저장된 전화가 없을 때 카카오에서 표시 시점에 찾은 전화(ADR-054 — 저장하지 않음). 영업 정보 항목을 펼쳤을
 * 때만 부른다(요청 절약, 웹 `useKakaoPhone`과 같다).
 */
export function useKakaoPhone(tripId: string, poiId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['poi', 'kakao-phone', tripId, poiId],
    queryFn: ({ signal }) => poiApi(apiClient).kakaoPhone(tripId, poiId, { signal }),
    enabled,
    retry: false,
    staleTime: Infinity,
  });
}
