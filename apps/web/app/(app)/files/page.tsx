'use client';

import { useEffect, useRef, useState } from 'react';
import { Download, Trash2 } from 'lucide-react';
import { ApiError, authApi } from '@pinvi/api-client';
import type { AttachmentLibraryItem } from '@pinvi/schemas';
import { apiClient } from '@/lib/api';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { ButtonLink, buttonClassName } from '@/components/ui/Button';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const scopeLabel: Record<AttachmentLibraryItem['target_scope'], string> = {
  trip: '여행',
  day: '날짜',
  poi: '장소',
  curated_plan: '추천 계획',
  curated_poi: '추천 장소',
};

export default function MyFilesPage() {
  const [items, setItems] = useState<AttachmentLibraryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AttachmentLibraryItem | null>(null);
  const deleteTriggerRef = useRef<HTMLElement | null>(null);
  const fileListRef = useRef<HTMLUListElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = async () => {
    const page = await authApi(apiClient).listFiles({ limit: 100 });
    setItems(page.items);
    setTotal(page.total);
  };

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        await reload();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : '파일을 불러오지 못했습니다.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  const download = async (attachmentId: string) => {
    setBusyId(attachmentId);
    setError(null);
    try {
      const res = await authApi(apiClient).fileDownloadUrl(attachmentId);
      window.open(res.download_url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '다운로드 링크를 만들지 못했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  // 파괴적·비가역(서버 삭제) — native confirm 대신 공용 확인 다이얼로그(DESIGN.md 확인 정책).
  const requestRemove = (item: AttachmentLibraryItem, trigger: HTMLElement | null) => {
    deleteTriggerRef.current = trigger;
    setError(null);
    setPendingDelete(item);
  };

  const confirmRemove = async () => {
    const target = pendingDelete;
    if (!target) return;
    setBusyId(target.attachment_id);
    setError(null);
    try {
      await authApi(apiClient).deleteFile(target.attachment_id);
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '삭제하지 못했습니다.');
    } finally {
      setBusyId(null);
      // 삭제에 성공하면 트리거(행 버튼)가 사라진다 — 포커스 복원 후보를 목록으로 바꾼다
      // (그대로 두면 분리된 노드라 폴백이 전부 탈락해 포커스가 body에 남는다, T-316 리뷰 P2).
      if (!deleteTriggerRef.current?.isConnected) deleteTriggerRef.current = fileListRef.current;
      // 요청이 끝난 뒤 닫는다 — 먼저 닫으면 busy 표시가 죽고 포커스 복원 폴백도 건너뛴다.
      setPendingDelete(null);
    }
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-ink">파일</h1>
        <p className="mt-1 text-sm text-muted">
          {total.toLocaleString('ko-KR')}개
          {!loading && total > items.length
            ? ` · 최근 ${items.length.toLocaleString('ko-KR')}개 표시`
            : ''}
        </p>
      </div>

      {error && (
        // 실패는 원인 + 회복 행동(DESIGN.md 상태 UI). role=alert로 스크린리더에도 전달한다.
        <p
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="my-file-error"
        >
          <span className="min-w-0">{error}</span>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setLoading(true);
              void reload()
                .catch((err) =>
                  setError(err instanceof ApiError ? err.message : '파일을 불러오지 못했습니다.'),
                )
                .finally(() => setLoading(false));
            }}
            className={buttonClassName({ variant: 'secondary', size: 'sm' })}
          >
            다시 시도
          </button>
        </p>
      )}

      {loading ? (
        // 형태가 정해진 목록은 spinner가 아니라 skeleton.
        <div
          className="overflow-hidden rounded-sm border border-hairline bg-canvas"
          aria-busy="true"
        >
          <span className="sr-only">파일 목록을 불러오는 중…</span>
          <ul className="m-0 list-none divide-y divide-hairline p-0">
            {[0, 1, 2].map((row) => (
              <li key={row} className="animate-pulse space-y-2 px-4 py-4">
                <div className="h-4 w-2/5 rounded-sm bg-surface-strong" />
                <div className="h-3 w-3/5 rounded-sm bg-surface-soft" />
              </li>
            ))}
          </ul>
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-sm border border-hairline bg-canvas p-6">
          <p className="text-sm font-semibold text-ink">업로드한 파일이 없습니다.</p>
          <p className="mt-1 text-sm text-muted">
            여행 상세에서 사진·영수증을 올리면 여기에 모입니다.
          </p>
          <ButtonLink href="/trips" variant="secondary" className="mt-4">
            여행으로 가기
          </ButtonLink>
        </div>
      ) : (
        <div className="overflow-hidden rounded-sm border border-hairline bg-canvas">
          <ul
            ref={fileListRef}
            tabIndex={-1}
            className="divide-y divide-hairline outline-hidden"
            data-testid="my-file-list"
          >
            {items.map((item) => (
              <li
                key={item.attachment_id}
                className="flex flex-wrap items-center justify-between gap-3 px-4 py-3"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-ink">
                    {item.original_filename}
                  </span>
                  <span className="text-xs text-muted">
                    {scopeLabel[item.target_scope]} · {item.trip_title ?? item.poi_label ?? '—'} ·{' '}
                    {formatBytes(item.byte_size)}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => void download(item.attachment_id)}
                    disabled={busyId === item.attachment_id}
                    aria-label="다운로드"
                    className="focus-ring inline-flex size-11 items-center justify-center rounded-sm text-muted hover:bg-surface-soft hover:text-ink disabled:opacity-50"
                  >
                    <Download className="h-4 w-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={(event) => requestRemove(item, event.currentTarget)}
                    disabled={busyId === item.attachment_id}
                    aria-label="삭제"
                    className="focus-ring inline-flex size-11 items-center justify-center rounded-sm text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete != null}
        tone="danger"
        title="이 파일 연결을 삭제할까요?"
        description={
          pendingDelete
            ? `${pendingDelete.original_filename} · 삭제하면 되돌릴 수 없습니다.`
            : undefined
        }
        confirmLabel="삭제"
        cancelLabel="취소"
        busy={busyId != null}
        onConfirm={() => void confirmRemove()}
        onCancel={() => setPendingDelete(null)}
        returnFocusRef={deleteTriggerRef}
        testId="file-delete-confirm"
      />
    </div>
  );
}
