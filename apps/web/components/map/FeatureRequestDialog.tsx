'use client';

import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, MapPin } from 'lucide-react';
import { ApiError, featureApi } from '@pinvi/api-client';
import type { FeatureSuggestionKind } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { buildNewPlaceRequest, type NewPlaceForm } from '@pinvi/domain';
import { FormField } from '@/components/forms/FormField';
import { FormTextArea } from '@/components/forms/FormTextArea';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

const DIALOG_LABEL = 'block text-sm font-semibold text-ink';

export interface FeatureRequestDialogProps {
  coord: { lon: number; lat: number };
  onClose: () => void;
  onSubmitted?: () => void;
  /** 진행 중 제안을 취소하고 닫았을 때 — 서버 접수 여부가 불확실함을 호출부가 안내한다. */
  onSubmitCancelled?: () => void;
}

const KINDS: { value: FeatureSuggestionKind; label: string }[] = [
  { value: 'place', label: '장소' },
  { value: 'event', label: '이벤트' },
];

export function FeatureRequestDialog({
  coord,
  onClose,
  onSubmitted,
  onSubmitCancelled,
}: FeatureRequestDialogProps) {
  const [form, setForm] = useState<NewPlaceForm>({
    kind: 'place',
    title: '',
    categories: '',
    note: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [titleError, setTitleError] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const titleRef = useRef<HTMLInputElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const submitAbortRef = useRef<AbortController | null>(null);

  // 접수 완료로 바뀌면 제출 버튼이 사라져 포커스가 body로 떨어진다 — 닫기로 옮긴다.
  useEffect(() => {
    if (done) closeRef.current?.focus();
  }, [done]);

  const update = (patch: Partial<NewPlaceForm>) => setForm((prev) => ({ ...prev, ...patch }));

  const submit = async () => {
    if (!form.title.trim()) {
      setTitleError('이름을 입력하세요.');
      titleRef.current?.focus();
      return;
    }
    setTitleError(undefined);
    const controller = new AbortController();
    submitAbortRef.current = controller;
    setSubmitting(true);
    setError(null);
    try {
      await featureApi(apiClient).request(buildNewPlaceRequest(form, coord), {
        signal: controller.signal,
      });
      setDone(true);
      onSubmitted?.();
    } catch (err) {
      if (controller.signal.aborted) return;
      setError(err instanceof ApiError ? err.message : '제안 등록에 실패했습니다.');
    } finally {
      if (submitAbortRef.current === controller) submitAbortRef.current = null;
      setSubmitting(false);
    }
  };

  // busy 중 닫기 = 진행 중 제안 등록 취소(T-316 요청 수명 계약 ⑤).
  // 서버가 이미 받았을 수 있으므로 호출부에 "결과 불확실"을 알린다(비멱등 POST, 리뷰 P1).
  const cancelSubmitAndClose = () => {
    const wasInFlight = submitAbortRef.current !== null;
    submitAbortRef.current?.abort();
    submitAbortRef.current = null;
    setSubmitting(false);
    onClose();
    if (wasInFlight) onSubmitCancelled?.();
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title="이 위치 장소 제안"
      description={
        <span className="flex items-center gap-1">
          <MapPin className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="font-mono">
            {coord.lat.toFixed(5)}, {coord.lon.toFixed(5)}
          </span>
        </span>
      }
      size="sm"
      busy={submitting}
      onCancelBusy={cancelSubmitAndClose}
      initialFocusRef={titleRef}
      testId="feature-request-dialog"
      footer={
        done ? (
          <Button ref={closeRef} onClick={onClose}>
            닫기
          </Button>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={submitting}>
              취소
            </Button>
            <Button
              onClick={() => void submit()}
              loading={submitting}
              data-testid="feature-request-submit"
            >
              제안하기
            </Button>
          </>
        )
      }
    >
      {done ? (
        <p className="flex items-center gap-2 rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">
          <CheckCircle2 className="size-4 shrink-0" aria-hidden="true" />
          제안이 접수됐습니다. 관리자 검토 후 반영됩니다.
        </p>
      ) : (
        <div className="space-y-3">
          <div className="flex gap-2" role="radiogroup" aria-label="종류">
            {KINDS.map((kind) => (
              <button
                key={kind.value}
                type="button"
                role="radio"
                aria-checked={form.kind === kind.value}
                onClick={() => update({ kind: kind.value })}
                className={
                  form.kind === kind.value
                    ? 'focus-ring min-h-11 flex-1 rounded-sm bg-ink text-sm font-semibold text-canvas'
                    : 'focus-ring min-h-11 flex-1 rounded-sm border border-hairline bg-canvas text-sm font-semibold text-ink hover:bg-surface-soft'
                }
              >
                {kind.label}
              </button>
            ))}
          </div>

          <FormField
            ref={titleRef}
            id="feature-request-title"
            label="이름"
            labelClassName={DIALOG_LABEL}
            value={form.title}
            onChange={(event) => update({ title: event.target.value })}
            maxLength={200}
            placeholder="예: 해운대 블루라인파크"
            error={titleError}
          />
          <FormField
            id="feature-request-categories"
            label="카테고리(쉼표 구분, 선택)"
            labelClassName={DIALOG_LABEL}
            value={form.categories}
            onChange={(event) => update({ categories: event.target.value })}
            placeholder="카페, 디저트"
          />
          <FormTextArea
            id="feature-request-note"
            label="메모(선택)"
            labelClassName={DIALOG_LABEL}
            value={form.note}
            onChange={(event) => update({ note: event.target.value })}
            maxLength={2000}
            rows={3}
          />

          {error && (
            <p role="alert" className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text">
              {error}
            </p>
          )}
        </div>
      )}
    </Dialog>
  );
}
