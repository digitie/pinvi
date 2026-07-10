'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2, MapPin } from 'lucide-react';
import { ApiError, geoApi } from '@pinvi/api-client';
import { apiClient } from '@/lib/api';
import { isAbortError } from '@/lib/abort';
import { useDialogAutoFocus } from '@/lib/useDialogAutoFocus';
import { useEscapeKey } from '@/lib/useEscapeKey';
import { FormField } from '@/components/forms/FormField';

const DIALOG_LABEL = 'block text-sm font-semibold text-ink';
const DIALOG_INPUT = 'h-9 px-2 focus:border-primary';

export type GeoCandidate = Record<string, unknown>;

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function cleanText(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null;
}

function firstText(source: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = cleanText(source[key]);
    if (value) return value;
  }
  return null;
}

function nestedAddressLabel(value: unknown): string | null {
  if (typeof value === 'string') return cleanText(value);
  if (!isRecord(value)) return null;
  return firstText(value, [
    'label',
    'full',
    'full_address',
    'road',
    'road_address',
    'jibun',
    'jibun_address',
    'addr',
    'name',
  ]);
}

function regionLabel(value: unknown): string | null {
  if (!isRecord(value)) return null;
  const direct = firstText(value, ['label', 'full_name', 'name', 'legal_dong_name', 'emd_name']);
  if (direct) return direct;
  const joined = [value.sido_name, value.sigungu_name, value.emd_name]
    .map(cleanText)
    .filter(Boolean)
    .join(' ');
  return joined || null;
}

export function geoCandidateAddressLabel(candidate: GeoCandidate | null): string | null {
  if (!candidate) return null;
  return (
    firstText(candidate, [
      'address_label',
      'road_address',
      'jibun_address',
      'full_address',
      'address_name',
      'addr',
    ]) ??
    nestedAddressLabel(candidate.address) ??
    regionLabel(candidate.region) ??
    cleanText(candidate.name) ??
    null
  );
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
  const [geoLoading, setGeoLoading] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [titleError, setTitleError] = useState<string | null>(null);

  useEscapeKey(onClose);
  useDialogAutoFocus(titleRef);

  useEffect(() => {
    const controller = new AbortController();
    setCandidate(null);
    setAddressLabel(null);
    setGeoError(null);
    setGeoLoading(true);

    void (async () => {
      try {
        const res = await geoApi(apiClient).reverse(
          { lon: coord.lon, lat: coord.lat, radiusM: 200 },
          { signal: controller.signal },
        );
        const first = res.candidates[0] ?? null;
        const label = geoCandidateAddressLabel(first);
        setCandidate(first);
        setAddressLabel(label);
        if (label && !titleTouchedRef.current) setTitle(label);
      } catch (err) {
        if (isAbortError(err)) return;
        setGeoError(err instanceof ApiError ? err.message : '주소를 확인하지 못했습니다.');
      } finally {
        if (!controller.signal.aborted) setGeoLoading(false);
      }
    })();

    return () => controller.abort();
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="POI 생성"
      data-testid="manual-poi-dialog"
    >
      <div className="w-full max-w-md space-y-4 rounded-md border border-hairline bg-white p-5 shadow-lg">
        <div className="flex items-center gap-2">
          <MapPin className="h-5 w-5 text-primary" aria-hidden="true" />
          <h2 className="text-base font-bold text-ink">POI 생성</h2>
        </div>

        <div className="rounded-sm bg-surface-soft px-3 py-2 text-xs text-muted">
          <p className="font-semibold text-ink">{dayLabel}</p>
          <p className="mt-1 font-mono">
            {coord.lat.toFixed(5)}, {coord.lon.toFixed(5)}
          </p>
        </div>

        <div className="space-y-1">
          <p className={DIALOG_LABEL}>주소</p>
          <p
            className="min-h-9 rounded-sm border border-hairline bg-white px-3 py-2 text-sm text-body"
            data-testid="manual-poi-address"
          >
            {geoLoading ? '주소 확인 중' : addressLabel ?? '주소 결과 없음'}
          </p>
          {geoError && <p className="text-xs text-error-text">{geoError}</p>}
        </div>

        <FormField
          ref={titleRef}
          id="manual-poi-title"
          label="이름"
          labelClassName={DIALOG_LABEL}
          className={DIALOG_INPUT}
          value={title}
          onChange={(event) => {
            setTitle(event.target.value);
            titleTouchedRef.current = true;
          }}
          error={titleError ?? undefined}
          maxLength={200}
        />

        {error && (
          <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft disabled:opacity-50"
          >
            취소
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={saving || geoLoading}
            data-testid="manual-poi-submit"
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            생성
          </button>
        </div>
      </div>
    </div>
  );
}
