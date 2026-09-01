'use client';

import { useEffect, useRef, useState } from 'react';
import { Download, Loader2, Save, Trash2 } from 'lucide-react';
import { ApiError, adminApi } from '@pinvi/api-client';
import type { AdminFileStorageSettings, AttachmentLibraryItem } from '@pinvi/schemas';
import { AdminPage, FilterBar, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FormTextArea } from '@/components/forms/FormTextArea';
import { apiClient } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { Dialog } from '@/components/ui/Dialog';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const scopeLabel: Record<AttachmentLibraryItem['target_scope'], string> = {
  trip: '여행',
  day: '날짜',
  poi: 'POI',
  curated_plan: '추천 계획',
  curated_poi: '추천 POI',
};

const scopeOptions: { value: '' | AttachmentLibraryItem['target_scope']; label: string }[] = [
  { value: '', label: '전체' },
  { value: 'trip', label: '여행' },
  { value: 'day', label: '날짜' },
  { value: 'poi', label: 'POI' },
  { value: 'curated_plan', label: '추천 계획' },
  { value: 'curated_poi', label: '추천 POI' },
];

export default function AdminFilesPage() {
  const [items, setItems] = useState<AttachmentLibraryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [settings, setSettings] = useState<AdminFileStorageSettings | null>(null);
  const [settingsDraft, setSettingsDraft] = useState({
    attachment_max_upload_bytes: '',
    trip_attachment_quota_bytes: '',
    user_attachment_quota_bytes: '',
  });
  const [settingsReason, setSettingsReason] = useState('');
  const [q, setQ] = useState('');
  const [scope, setScope] = useState<'' | AttachmentLibraryItem['target_scope']>('');
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<AttachmentLibraryItem | null>(null);
  const [deleteReason, setDeleteReason] = useState('');
  const [deleteReasonError, setDeleteReasonError] = useState<string | null>(null);
  const deleteTriggerRef = useRef<HTMLElement | null>(null);
  const fileSectionRef = useRef<HTMLDivElement | null>(null);
  const deleteReasonRef = useRef<HTMLTextAreaElement | null>(null);

  const loadFiles = async () => {
    const page = await adminApi(apiClient).listFiles({
      q: q.trim() || undefined,
      scope: scope || undefined,
      limit: 100,
    });
    setItems(page.items);
    setTotal(page.total);
  };

  useEffect(() => {
    let cancelled = false;
    const admin = adminApi(apiClient);
    Promise.all([admin.listFiles({ limit: 100 }), admin.getFileSettings()])
      .then(([filePage, nextSettings]) => {
        if (cancelled) return;
        setItems(filePage.items);
        setTotal(filePage.total);
        setSettings(nextSettings);
        setSettingsDraft({
          attachment_max_upload_bytes: String(nextSettings.attachment_max_upload_bytes),
          trip_attachment_quota_bytes: String(nextSettings.trip_attachment_quota_bytes),
          user_attachment_quota_bytes: String(nextSettings.user_attachment_quota_bytes),
        });
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : '파일 정보를 불러오지 못했습니다.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const applyFilter = async () => {
    setLoading(true);
    setError(null);
    try {
      await loadFiles();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '파일 목록을 불러오지 못했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const download = async (attachmentId: string) => {
    setBusyId(attachmentId);
    setError(null);
    try {
      const res = await adminApi(apiClient).fileDownloadUrl(attachmentId);
      window.open(res.download_url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '다운로드 링크를 만들지 못했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  // 사유를 받아야 하는 파괴적 액션 — native prompt 대신 사유 입력 Dialog(DESIGN.md 확인 정책).
  const requestRemove = (item: AttachmentLibraryItem, trigger: HTMLElement | null) => {
    deleteTriggerRef.current = trigger;
    setDeleteReason('');
    setDeleteReasonError(null);
    setError(null);
    setPendingDelete(item);
  };

  const remove = async () => {
    const target = pendingDelete;
    if (!target) return;
    const reason = deleteReason.trim();
    if (!reason) {
      setDeleteReasonError('삭제 사유를 입력하세요.');
      return;
    }
    setBusyId(target.attachment_id);
    setDeleteReasonError(null);
    setError(null);
    try {
      await adminApi(apiClient).deleteFile(target.attachment_id, { access_reason: reason });
      await loadFiles();
      // 삭제된 행의 버튼은 사라진다 — 포커스는 표 컨테이너가 받는다.
      if (!deleteTriggerRef.current?.isConnected) deleteTriggerRef.current = fileSectionRef.current;
      setPendingDelete(null);
    } catch (err) {
      // 실패하면 다이얼로그를 열어 둔 채 원인을 그 안에서 알린다(입력 보존).
      setDeleteReasonError(err instanceof ApiError ? err.message : '삭제하지 못했습니다.');
    } finally {
      setBusyId(null);
    }
  };

  const saveSettings = async () => {
    setSettingsBusy(true);
    setError(null);
    try {
      const updated = await adminApi(apiClient).updateFileSettings({
        attachment_max_upload_bytes: Number(settingsDraft.attachment_max_upload_bytes),
        trip_attachment_quota_bytes: Number(settingsDraft.trip_attachment_quota_bytes),
        user_attachment_quota_bytes: Number(settingsDraft.user_attachment_quota_bytes),
        access_reason: settingsReason.trim(),
      });
      setSettings(updated);
      setSettingsReason('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '설정을 저장하지 못했습니다.');
    } finally {
      setSettingsBusy(false);
    }
  };

  const columns: AdminTableColumn<AttachmentLibraryItem>[] = [
    {
      key: 'file',
      header: '파일',
      cell: (row) => (
        <span>
          <span className="block font-semibold text-ink">{row.original_filename}</span>
          <span className="block text-xs text-muted">
            {row.content_type} · {formatBytes(row.byte_size)}
          </span>
        </span>
      ),
    },
    {
      key: 'scope',
      header: '대상',
      cell: (row) => (
        <span>
          <span className="block">{scopeLabel[row.target_scope]}</span>
          <span className="block text-xs text-muted">{row.trip_title ?? row.poi_label ?? '—'}</span>
        </span>
      ),
    },
    {
      key: 'uploader',
      header: '업로더',
      cell: (row) => row.uploaded_by_email_masked ?? row.uploaded_by_user_id,
    },
    {
      key: 'created_at',
      header: '등록',
      sortable: true,
      sortValue: (row) => new Date(row.created_at).getTime(),
      cell: (row) => new Date(row.created_at).toLocaleString('ko-KR'),
    },
    {
      key: 'actions',
      header: '',
      cell: (row) => (
        <span className="flex justify-end gap-1">
          <button
            type="button"
            onClick={() => void download(row.attachment_id)}
            disabled={busyId === row.attachment_id}
            aria-label="다운로드"
            className="rounded-sm p-2 text-muted hover:bg-surface-soft hover:text-ink disabled:opacity-50"
          >
            <Download className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={(event) => requestRemove(row, event.currentTarget)}
            disabled={busyId === row.attachment_id}
            aria-label="삭제"
            className="rounded-sm p-2 text-muted hover:bg-error-bg hover:text-error-text disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        </span>
      ),
    },
  ];

  return (
    <AdminPage title="파일" description="여행/날짜/POI 첨부 관리">
      {error && <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>}

      <Section title="전역 용량 정책">
        <div className="grid gap-3 lg:grid-cols-4">
          {(
            [
              ['attachment_max_upload_bytes', '개별 파일'],
              ['trip_attachment_quota_bytes', '계획 총량'],
              ['user_attachment_quota_bytes', '사용자 총량'],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="text-sm">
              <span className="mb-1 block text-xs font-semibold text-muted">{label}</span>
              <input
                value={settingsDraft[key]}
                onChange={(e) => setSettingsDraft((prev) => ({ ...prev, [key]: e.target.value }))}
                inputMode="numeric"
                className="h-10 w-full rounded-sm border border-hairline px-3"
                data-testid={`admin-file-setting-${key}`}
              />
              {settings && (
                <span className="mt-1 block text-xs text-muted">{formatBytes(settings[key])}</span>
              )}
            </label>
          ))}
          <div className="space-y-2">
            <FormTextArea
              id="admin-file-settings-reason"
              label="사유"
              value={settingsReason}
              onChange={(e) => setSettingsReason(e.target.value)}
              rows={2}
            />
            <button
              type="button"
              onClick={saveSettings}
              disabled={settingsBusy || settingsReason.trim().length < 1}
              className="inline-flex h-10 items-center gap-2 rounded-sm bg-cta hover:bg-cta-hover px-3 text-sm font-semibold text-on-primary disabled:opacity-50"
              data-testid="admin-file-settings-save"
            >
              {settingsBusy ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Save className="h-4 w-4" aria-hidden="true" />
              )}
              저장
            </button>
          </div>
        </div>
      </Section>

      <FilterBar>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="파일명, 여행명, 이메일"
          className="h-10 min-w-64 rounded-sm border border-hairline px-3 text-sm"
          data-testid="admin-files-search"
        />
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value as '' | AttachmentLibraryItem['target_scope'])}
          className="h-10 rounded-sm border border-hairline px-3 text-sm"
          data-testid="admin-files-scope"
        >
          {scopeOptions.map((option) => (
            <option key={option.value || 'all'} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={applyFilter}
          className="h-10 rounded-sm border border-primary px-3 text-sm font-semibold text-primary"
          data-testid="admin-files-search-submit"
        >
          검색
        </button>
        <span className="text-sm text-muted">{total.toLocaleString('ko-KR')}개</span>
      </FilterBar>

      {loading ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
          불러오는 중…
        </div>
      ) : (
        // 삭제 성공 후 행 버튼이 사라지면 포커스가 이 컨테이너로 돌아온다.
        <div ref={fileSectionRef} tabIndex={-1} className="outline-hidden">
          <AdminTable
            columns={columns}
            rows={items}
            rowKey={(row) => row.attachment_id}
            empty="파일이 없습니다."
          />
        </div>
      )}
      <Dialog
        open={pendingDelete != null}
        onClose={() => setPendingDelete(null)}
        busy={busyId != null}
        size="sm"
        title="파일을 삭제할까요?"
        description={pendingDelete?.original_filename}
        initialFocusRef={deleteReasonRef}
        returnFocusRef={deleteTriggerRef}
        testId="admin-file-delete-dialog"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setPendingDelete(null)}
              disabled={busyId != null}
            >
              취소
            </Button>
            <Button
              variant="danger"
              onClick={() => void remove()}
              loading={busyId != null}
              data-testid="admin-file-delete-submit"
            >
              삭제
            </Button>
          </>
        }
      >
        <FormTextArea
          ref={deleteReasonRef}
          id="admin-file-delete-reason"
          label="삭제 사유"
          hint="audit log에 남습니다."
          value={deleteReason}
          onChange={(event) => {
            if (deleteReasonError) setDeleteReasonError(null);
            setDeleteReason(event.target.value);
          }}
          error={deleteReasonError ?? undefined}
          disabled={busyId != null}
          maxLength={500}
          rows={3}
          data-testid="admin-file-delete-reason"
        />
      </Dialog>
    </AdminPage>
  );
}
