'use client';

import { FormField } from '@/components/forms/FormField';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import { isAbortError } from '@/lib/abort';
import { apiClient } from '@/lib/api';
import { type GeoCandidate, geoCandidateAddressLabel } from '@/lib/geoCandidateAddressLabel';
import { ApiError, geoApi } from '@pinvi/api-client';
import { useEffect, useRef, useState } from 'react';

const DIALOG_LABEL = 'block text-sm font-semibold text-ink';

export interface ManualPoiCreateInput {
  title: string;
  coord: { lon: number; lat: number };
  addressLabel: string | null;
  candidate: GeoCandidate | null;
}

export interface TripManualPoiDialogProps {
  coord: { lon: number; lat: number };
  dayLabel: string;
  saving?: boolean;
  error?: string | null;
  onClose: () => void;
  onCreate: (input: ManualPoiCreateInput) => Promise<boolean>;
}

export function TripManualPoiDialog({
  coord,
  dayLabel,
  saving = false,
  error = null,
  onClose,
  onCreate,
}: TripManualPoiDialogProps) {
  const titleRef = useRef<HTMLInputElement>(null);
  const titleTouchedRef = useRef(false);
  const [title, setTitle] = useState('');
  const [candidate, setCandidate] = useState<GeoCandidate | null>(null);
  const [addressLabel, setAddressLabel] = useState<string | null>(null);
  const [geoLoading, setGeoLoading] = useState(true);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [titleError, setTitleError] = useState<string | null>(null);

  // 렌더 중 prop 변화에 맞춰 state 조정 패턴 — 좌표가 바뀔 때만 이전 조회 결과를 리셋한다.
  // 실제 조회(부수효과)는 아래 effect가 담당한다.
  const [syncedCoord, setSyncedCoord] = useState(coord);
  if (coord.lat !== syncedCoord.lat || coord.lon !== syncedCoord.lon) {
    setSyncedCoord(coord);
    setCandidate(null);
    setAddressLabel(null);
    setGeoError(null);
    setGeoLoading(true);
  }

  useEffect(() => {
    const controller = new AbortController();
    let active = true;

    void (async () => {
      try {
        const res = await geoApi(apiClient).reverse(
          // 지도에서 고른 지점이다 — 단말 위치가 아니므로 위치 동의를 요구하지 않는다(T-329).
          { lon: coord.lon, lat: coord.lat, radiusM: 200, coordSource: 'map_pick' },
          { signal: controller.signal },
        );
        if (!active) return;
        const first = res.candidates[0] ?? null;
        const label = geoCandidateAddressLabel(first);
        setCandidate(first);
        setAddressLabel(label);
        if (label && !titleTouchedRef.current) setTitle(label);
      } catch (err) {
        if (!active) return;
        if (isAbortError(err)) return;
        setGeoError(err instanceof ApiError ? err.message : '주소를 확인하지 못했습니다.');
      } finally {
        if (active) setGeoLoading(false);
      }
    })();

    return () => {
      active = false;
      controller.abort();
    };
  }, [coord.lat, coord.lon]);

  const submit = async () => {
    const trimmed = title.trim();
    const effectiveTitle = trimmed || addressLabel;
    if (!effectiveTitle) {
      setTitleError('이름을 입력하세요.');
      titleRef.current?.focus();
      return;
    }
    setTitleError(null);
    await onCreate({
      title: effectiveTitle,
      coord,
      addressLabel,
      candidate,
    });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title="POI 생성"
      size="sm"
      busy={saving}
      initialFocusRef={titleRef}
      testId="manual-poi-dialog"
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>
            취소
          </Button>
          <Button
            onClick={() => void submit()}
            disabled={geoLoading}
            loading={saving}
            data-testid="manual-poi-submit"
          >
            생성
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div className="rounded-sm bg-surface-soft px-3 py-2 text-xs text-muted">
          <p className="font-semibold text-ink">{dayLabel}</p>
          <p className="mt-1 font-mono">
            {coord.lat.toFixed(5)}, {coord.lon.toFixed(5)}
          </p>
        </div>

        <div className="space-y-1">
          <p className={DIALOG_LABEL}>주소</p>
          <p
            className="min-h-11 rounded-sm border border-hairline bg-canvas px-3 py-2 text-sm text-body"
            data-testid="manual-poi-address"
            aria-busy={geoLoading || undefined}
          >
            {geoLoading ? '주소 확인 중…' : (addressLabel ?? '주소 결과 없음')}
          </p>
          {geoError && <p className="text-xs text-error-text">{geoError}</p>}
        </div>

        <FormField
          ref={titleRef}
          id="manual-poi-title"
          label="이름"
          labelClassName={DIALOG_LABEL}
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
            titleTouchedRef.current = true;
          }}
          error={titleError ?? undefined}
          maxLength={200}
        />

        {error && (
          <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
            {error}
          </p>
        )}
      </div>
    </Dialog>
  );
}
