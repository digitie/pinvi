'use client';

import { Loader2, MapPin } from 'lucide-react';
import { useEscapeKey } from '@/lib/useEscapeKey';

export interface LocationConsentDialogProps {
  open: boolean;
  saving?: boolean;
  error?: string | null;
  onAgree: () => void;
  onCancel: () => void;
}

export function LocationConsentDialog({
  open,
  saving = false,
  error = null,
  onAgree,
  onCancel,
}: LocationConsentDialogProps) {
  useEscapeKey(onCancel, open);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-label="위치정보 이용 동의"
      data-testid="location-consent-dialog"
    >
      <div className="w-full max-w-md space-y-4 rounded-md border border-hairline bg-white p-5 shadow-lg">
        <div className="flex items-center gap-2">
          <MapPin className="h-5 w-5 text-primary" aria-hidden="true" />
          <h2 className="text-base font-bold text-ink">위치정보 이용 동의</h2>
        </div>
        <div className="space-y-2 text-sm text-body">
          <p>내 위치 표시·주변 검색 등 위치 기반 기능을 사용하려면 아래 동의가 필요합니다.</p>
          <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
            <li>위치기반서비스 이용약관(필수)</li>
            <li>개인위치정보 수집·이용(필수)</li>
          </ul>
          <p className="text-xs text-muted">
            동의는 설정에서 언제든 철회할 수 있으며, 철회 시 위치 기능이 비활성화됩니다(위치정보법
            제16조).
          </p>
        </div>
        {error && (
          <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-xs text-error-text">{error}</p>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="h-9 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink hover:bg-surface-soft"
          >
            취소
          </button>
          <button
            type="button"
            onClick={onAgree}
            disabled={saving}
            data-testid="location-consent-agree"
            className="inline-flex h-9 items-center gap-1 rounded-sm bg-primary px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            동의하고 사용
          </button>
        </div>
      </div>
    </div>
  );
}
