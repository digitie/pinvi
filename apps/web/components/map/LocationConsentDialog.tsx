'use client';

import { MapPin } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

export interface LocationConsentDialogProps {
  open: boolean;
  saving?: boolean;
  error?: string | null;
  onAgree: () => void;
  onCancel: () => void;
}

/**
 * 위치 기능 사용 전 동의 게이트(위치정보법 제16조). 모달 셸·focus trap·scroll lock은
 * `Dialog` 프리미티브가 담당한다(이전에는 `useEscapeKey`만 있어 focus trap이 없었다).
 */
export function LocationConsentDialog({
  open,
  saving = false,
  error = null,
  onAgree,
  onCancel,
}: LocationConsentDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      busy={saving}
      size="sm"
      testId="location-consent-dialog"
      title={
        <span className="flex items-center gap-2">
          <MapPin className="size-5 text-primary" aria-hidden="true" />
          위치정보 이용 동의
        </span>
      }
      footer={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={saving}>
            취소
          </Button>
          <Button onClick={onAgree} loading={saving} data-testid="location-consent-agree">
            동의하고 사용
          </Button>
        </>
      }
    >
      <div className="space-y-2 text-sm text-body">
        <p>내 위치 표시·주변 검색 등 위치 기반 기능을 사용하려면 아래 동의가 필요합니다.</p>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          <li>위치기반서비스 이용약관(필수)</li>
          <li>개인위치정보 수집·이용(필수)</li>
        </ul>
        <p className="text-sm text-muted">
          동의는 설정에서 언제든 철회할 수 있으며, 철회 시 위치 기능이 비활성화됩니다(위치정보법
          제16조).
        </p>
      </div>
      {error ? (
        <p role="alert" className="mt-3 rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
          {error}
        </p>
      ) : null}
    </Dialog>
  );
}
