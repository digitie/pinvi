import { create } from 'zustand';

/** UI 보조 상태 — 사이드 패널, 모달, 토스트 큐 등. */
interface UiState {
  isSidePanelOpen: boolean;
  selectedTripId: string | null;
  selectedPoiId: string | null;
  setSidePanel: (open: boolean) => void;
  selectTrip: (tripId: string | null) => void;
  selectPoi: (poiId: string | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  isSidePanelOpen: true,
  selectedTripId: null,
  selectedPoiId: null,
  setSidePanel: (open) => set({ isSidePanelOpen: open }),
  selectTrip: (tripId) => set({ selectedTripId: tripId, selectedPoiId: null }),
  selectPoi: (poiId) => set({ selectedPoiId: poiId }),
}));
