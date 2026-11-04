'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi, ApiError } from '@pinvi/api-client';
import { apiClient } from '@/lib/api';
import { Section } from '@/components/admin/AdminPage';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { buttonClassName } from '@/components/ui/Button';

const key = ['admin', 'storage-retention'] as const;
const reasons: Record<string, string> = {
  AccessDenied: '저장소 삭제 권한을 확인해 주세요.',
  InvalidAccessKeyId: '저장소 접근 키 설정을 확인해 주세요.',
  SignatureDoesNotMatch: '저장소 인증 설정을 확인해 주세요.',
  NoSuchBucket: '파일 버킷 설정을 확인해 주세요.',
  STORAGE_UNAVAILABLE: '저장소 연결이 실패했습니다. 연결을 복구한 뒤 재시도해 주세요.',
};

export function StorageRetentionPanel() {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState('');
  const [phrase, setPhrase] = useState('');
  const [confirm, setConfirm] = useState(false);
  const summary = useQuery({ queryKey: key, queryFn: () => adminApi(apiClient).getStorageRetention() });
  const run = useMutation({
    mutationFn: () => adminApi(apiClient).executeStorageRetention({
      access_reason: reason.trim(), confirm_phrase: 'DELETE EXPIRED FILES',
    }),
    onSuccess: () => { setConfirm(false); setPhrase(''); },
    onSettled: () => { void queryClient.invalidateQueries({ queryKey: key }); },
  });
  const data = summary.data;
  const error = run.error ?? summary.error;
  return <Section title="여행 휴지통·첨부 정리">
    <div className="space-y-4" data-testid="storage-retention">
      <p className="text-sm text-muted">휴지통의 여행은 삭제 후 30일까지 복원할 수 있습니다. 정리를 실행하면 기한이 지난 여행과 삭제 파일을 영구 정리합니다. 다른 여행·추천 자료에서 사용하는 파일은 보존합니다.</p>
      {summary.isPending ? <p role="status">정리 상태를 확인하는 중…</p> : data && <>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[['기한 지난 여행', data.expired_trips], ['정리 대상 첨부', data.eligible_attachments],
            ['만료된 미등록 업로드', data.expired_uploads], ['정리 대기 파일', data.pending_objects]].map(([label, value]) =>
            <div key={label}><dt className="text-sm text-muted">{label}</dt><dd className="font-semibold">{value}</dd></div>)}
        </dl>
        {data.in_progress_objects > 0 && <p role="status" className="text-sm text-muted">{data.in_progress_objects}개 파일을 다른 실행에서 처리 중입니다.</p>}
        {data.errors.map((item) => <p key={item.code} role="alert" className="text-sm text-error-text">
          {item.count}개 파일 정리 실패 · {item.code}: {reasons[item.code] ?? '저장소의 오류를 확인한 뒤 재시도해 주세요.'} 삭제 확인 전까지 사용 용량을 유지합니다.
        </p>)}
      </>}
      {error && <p role="alert" className="text-sm text-error-text">{error instanceof ApiError ? error.message : '정리 작업을 확인하지 못했습니다.'} 상태를 다시 확인한 뒤 재시도해 주세요.</p>}
      {run.data && <p role="status" className="text-sm text-muted">
        여행 {run.data.trips_deleted}개·파일 {run.data.objects_deleted}개 정리, 파일 {run.data.objects_failed}개 실패.
        {run.data.status.pending_objects > 0 || run.data.status.eligible_attachments > 0 || run.data.status.expired_trips > 0 ? ' 남은 항목은 다시 실행해 정리할 수 있습니다.' : ' 현재 정리 대기 항목이 없습니다.'}
      </p>}
      <button type="button" className={buttonClassName({ variant: 'ghost' })} disabled={summary.isFetching || run.isPending} onClick={() => void summary.refetch()}>상태 새로고침</button>
      {data?.can_execute && <div className="space-y-3">
        <label className="block text-sm">정리 사유
          <textarea className="mt-1 block min-h-20 w-full rounded-sm border border-hairline p-3" value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} disabled={run.isPending} />
        </label>
        <label className="block text-sm">확인 문구: DELETE EXPIRED FILES
          <input className="mt-1 block min-h-11 w-full rounded-sm border border-hairline px-3" value={phrase} onChange={(e) => setPhrase(e.target.value)} disabled={run.isPending} />
        </label>
        <button type="button" className={buttonClassName({ variant: 'danger' })} disabled={run.isPending || reason.trim().length < 5 || phrase !== 'DELETE EXPIRED FILES'} onClick={() => setConfirm(true)}>기한 지난 여행·파일 정리</button>
      </div>}
      <ConfirmDialog open={confirm} title="보관 기한이 지난 여행과 파일을 정리할까요?" tone="danger"
        description="정리가 시작된 여행은 복원할 수 없습니다. 삭제 실패는 기록되며 다음 실행에서 재시도합니다."
        confirmLabel="영구 정리 실행" busy={run.isPending} onCancel={() => setConfirm(false)} onConfirm={() => run.mutate()} testId="storage-retention-confirm" />
    </div>
  </Section>;
}
