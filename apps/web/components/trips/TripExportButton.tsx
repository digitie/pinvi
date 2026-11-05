'use client';

import { useEffect, useRef, useState } from 'react';
import { Download, Printer } from 'lucide-react';
import type { TripView } from '@pinvi/schemas';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';
import {
  buildTripCalendar,
  buildTripExport,
  exportFilename,
  type TripExportModel,
} from '@/lib/tripExport';
import { openTripPrintWindow } from '@/lib/tripPrintWindow';
import { TripExportDocument } from './TripExportDocument';

export function TripExportButton({
  view,
  compact = false,
}: {
  view: Pick<TripView, 'trip' | 'days'>;
  compact?: boolean;
}) {
  const [model, setModel] = useState<TripExportModel | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const documentRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const calendar = model ? buildTripCalendar(model) : null;
  const close = () => {
    controller.current?.abort();
    setModel(null);
    setError(null);
  };
  const print = async () => {
    if (!documentRef.current || busy || !model) return;
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true);
    setError(null);
    try {
      await openTripPrintWindow(documentRef.current, model.title + ' - 여행 일정', abort.signal);
    } catch (reason) {
      if (!abort.signal.aborted)
        setError(reason instanceof Error ? reason.message : '인쇄창을 준비하지 못했습니다.');
    } finally {
      if (controller.current === abort) controller.current = null;
      setBusy(false);
    }
  };
  const download = () => {
    if (!calendar || !model || calendar.events === 0) return;
    const url = URL.createObjectURL(
      new Blob([calendar.content], { type: 'text/calendar;charset=utf-8' }),
    );
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = exportFilename(model.title, 'ics');
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return (
    <>
      <Button
        ref={triggerRef}
        variant="secondary"
        size="sm"
        aria-label="여행 내보내기"
        title="여행 내보내기"
        leadingIcon={compact ? undefined : <Download className="h-4 w-4" aria-hidden="true" />}
        data-testid="trip-export-open"
        className={compact ? 'min-h-11 w-11 shrink-0 px-0' : undefined}
        onClick={() => {
          setModel(buildTripExport(view));
          setError(null);
        }}
      >
        {compact ? <Download className="h-4 w-4" aria-hidden="true" /> : '내보내기'}
      </Button>
      <Dialog
        open={model !== null}
        onClose={close}
        title="여행 내보내기"
        size="lg"
        description="선택·숨김 상태와 관계없이 조회된 전체 일자를 포함합니다. 인쇄창에서 프린터 또는 PDF 저장을 선택하세요."
        returnFocusRef={triggerRef}
        busy={busy}
        onCancelBusy={close}
        testId="trip-export-dialog"
        footer={
          <>
            <Button
              variant="secondary"
              size="sm"
              disabled={!calendar?.events || busy}
              onClick={download}
              data-testid="trip-export-ics"
            >
              ICS 다운로드
            </Button>
            <Button
              size="sm"
              loading={busy}
              onClick={() => void print()}
              data-testid="trip-export-print"
              leadingIcon={<Printer className="h-4 w-4" aria-hidden="true" />}
            >
              인쇄 / PDF 저장
            </Button>
          </>
        }
      >
        {error && (
          <p role="alert" className="mb-3 rounded-sm bg-error-bg p-3 text-sm text-error-text">
            {error}
          </p>
        )}
        {calendar && (
          <p className="mb-3 text-sm text-muted" data-testid="trip-export-calendar-summary">
            캘린더에 {calendar.events}개 일정이 포함됩니다.
            {calendar.omitted > 0 && ` 날짜·시각 미정 ${calendar.omitted}개는 ICS에서 제외됩니다.`}
            {calendar.invalidEnds > 0 &&
              ` 출발이 도착보다 늦지 않은 ${calendar.invalidEnds}개는 종료 시각을 넣지 않습니다.`}
          </p>
        )}
        <div ref={documentRef}>{model && <TripExportDocument model={model} />}</div>
      </Dialog>
    </>
  );
}
