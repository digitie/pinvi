'use client';

/* eslint-disable @next/next/no-img-element */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { type ChangeEvent, useEffect, useState } from 'react';
import {
  Eraser,
  ImageIcon,
  KeyRound,
  Loader2,
  LogOut,
  Mail,
  RotateCcw,
  ShieldCheck,
  Trash2,
  Upload,
  UserX,
} from 'lucide-react';
import { ApiClient, ApiError, adminApi } from '@pinvi/api-client';
import { putToPresigned } from '@pinvi/domain';
import type {
  AdminAuditEntry,
  AdminAvatarSettings,
  AdminUserDetail,
  AdminUserSessionRecord,
  MutableAdminRole,
} from '@pinvi/schemas';
import { AdminPage, Section } from '@/components/admin/AdminPage';
import { AdminTable, type AdminTableColumn } from '@/components/admin/AdminTable';
import { FormTextArea } from '@/components/forms/FormTextArea';

const apiClient = new ApiClient({
  baseUrl: process.env.NEXT_PUBLIC_PINVI_API_URL ?? 'http://localhost:12801',
});

type ActionKind = 'force-verify' | 'disable' | 'reveal-email';
type LifecycleActionKind =
  | 'resend-verify'
  | 'force-password-reset'
  | 'revoke-all'
  | 'reactivate'
  | 'delete'
  | 'anonymize';

const ROLE_OPTIONS: { value: MutableAdminRole; label: string }[] = [
  { value: 'admin', label: 'admin' },
  { value: 'operator', label: 'operator' },
  { value: 'cpo', label: 'cpo' },
];

function formatBytes(value: number | null | undefined) {
  if (!value) {
    return '크기 기록 없음';
  }
  if (value < 1024 * 1024) {
    return `${Math.round(value / 1024)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

const auditColumns: AdminTableColumn<AdminAuditEntry>[] = [
  {
    key: 'action',
    header: '액션',
    cell: (row) => <span className="font-mono text-xs">{row.action}</span>,
  },
  {
    key: 'access_reason',
    header: '사유',
    cell: (row) => row.access_reason ?? '—',
  },
  {
    key: 'target_pii_fields',
    header: 'PII',
    cell: (row) => row.target_pii_fields?.join(', ') ?? '—',
  },
  {
    key: 'occurred_at',
    header: '시각',
    sortable: true,
    sortValue: (row) => new Date(row.occurred_at).getTime(),
    cell: (row) => (
      <span className="text-muted">{new Date(row.occurred_at).toLocaleString('ko-KR')}</span>
    ),
  },
];

export default function AdminUserDetailPage() {
  const router = useRouter();
  const params = useParams<{ user_id: string }>();
  const userId = params.user_id;
  const [user, setUser] = useState<AdminUserDetail | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionDialog, setActionDialog] = useState<ActionKind | null>(null);
  const [reason, setReason] = useState('');
  const [acting, setActing] = useState(false);
  const [avatarSrc, setAvatarSrc] = useState<string | null>(null);
  const [avatarAction, setAvatarAction] = useState<'upload' | 'delete' | 'settings' | null>(null);
  const [avatarReason, setAvatarReason] = useState('');
  const [avatarSettings, setAvatarSettings] = useState<AdminAvatarSettings | null>(null);
  const [avatarMaxBytes, setAvatarMaxBytes] = useState('');
  const [settingsReason, setSettingsReason] = useState('');
  const [quotaDraft, setQuotaDraft] = useState({
    attachment_max_upload_bytes_override: '',
    trip_attachment_quota_bytes_override: '',
    user_attachment_quota_bytes_override: '',
  });
  const [quotaReason, setQuotaReason] = useState('');
  const [quotaBusy, setQuotaBusy] = useState(false);
  const [roleDraft, setRoleDraft] = useState<MutableAdminRole>('operator');
  const [roleReason, setRoleReason] = useState('');
  const [roleBusy, setRoleBusy] = useState<'grant' | 'revoke' | null>(null);
  const [sessions, setSessions] = useState<AdminUserSessionRecord[]>([]);
  const [lifecycleReason, setLifecycleReason] = useState('');
  const [lifecycleBusy, setLifecycleBusy] = useState<LifecycleActionKind | null>(null);
  const [sessionBusy, setSessionBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const api = adminApi(apiClient);
    const load = async () => {
      try {
        const [nextUser, nextSettings, nextSessions] = await Promise.all([
          api.getUser(userId),
          api.getAvatarSettings(),
          api.listUserSessions(userId),
        ]);
        if (cancelled) return;
        setUser(nextUser);
        setSessions(nextSessions.items);
        setQuotaDraft({
          attachment_max_upload_bytes_override: nextUser.file_quota
            .attachment_max_upload_bytes_override
            ? String(nextUser.file_quota.attachment_max_upload_bytes_override)
            : '',
          trip_attachment_quota_bytes_override: nextUser.file_quota
            .trip_attachment_quota_bytes_override
            ? String(nextUser.file_quota.trip_attachment_quota_bytes_override)
            : '',
          user_attachment_quota_bytes_override: nextUser.file_quota
            .user_attachment_quota_bytes_override
            ? String(nextUser.file_quota.user_attachment_quota_bytes_override)
            : '',
        });
        setAvatarSettings(nextSettings);
        setAvatarMaxBytes(String(nextSettings.avatar_max_upload_bytes));
        if (!nextUser.has_avatar) {
          setAvatarSrc(null);
          return;
        }
        try {
          const avatar = await api.getUserAvatarDownloadUrl(userId);
          if (!cancelled) setAvatarSrc(avatar.public_url ?? avatar.download_url);
        } catch {
          if (!cancelled) setAvatarSrc(null);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 404) {
          router.replace('/admin/users');
          return;
        }
        setError(err instanceof ApiError ? err.message : '조회 실패');
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [userId, router]);

  const onAction = async () => {
    if (!actionDialog || reason.trim().length < 1) return;
    setActing(true);
    try {
      const api = adminApi(apiClient);
      const accessReason = reason.trim();
      const updated =
        actionDialog === 'reveal-email'
          ? await api.revealUserPii(userId, { access_reason: accessReason })
          : actionDialog === 'force-verify'
            ? await api.forceVerify(userId, { access_reason: accessReason })
            : await api.disableUser(userId, { access_reason: accessReason });
      setUser(updated);
      setActionDialog(null);
      setReason('');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '액션 실패');
    } finally {
      setActing(false);
    }
  };

  const refreshAvatarUrl = async (nextUser: AdminUserDetail) => {
    if (!nextUser.has_avatar) {
      setAvatarSrc(null);
      return;
    }
    try {
      const avatar = await adminApi(apiClient).getUserAvatarDownloadUrl(userId);
      setAvatarSrc(avatar.public_url ?? avatar.download_url);
    } catch {
      setAvatarSrc(null);
    }
  };

  const onAvatarFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    event.target.value = '';
    if (!file) return;
    const accessReason = avatarReason.trim();
    if (accessReason.length < 1) {
      setError('아바타 변경 사유가 필요합니다.');
      return;
    }
    if (!file.type.startsWith('image/')) {
      setError('아바타는 이미지 파일만 업로드할 수 있습니다.');
      return;
    }
    setAvatarAction('upload');
    setError(null);
    setMessage(null);
    try {
      const api = adminApi(apiClient);
      const upload = await api.createUserAvatarUploadUrl(userId, {
        filename: file.name,
        content_type: file.type,
        content_length: file.size,
      });
      await putToPresigned(upload, file);
      const updated = await api.updateUserAvatar(userId, {
        bucket: upload.bucket,
        storage_key: upload.storage_key,
        content_type: file.type,
        byte_size: file.size,
        public_url: upload.public_url ?? null,
        access_reason: accessReason,
      });
      setUser(updated);
      setAvatarReason('');
      setMessage('아바타를 저장했습니다.');
      await refreshAvatarUrl(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '아바타를 저장하지 못했습니다.');
    } finally {
      setAvatarAction(null);
    }
  };

  const onDeleteAvatar = async () => {
    const accessReason = avatarReason.trim();
    if (accessReason.length < 1) {
      setError('아바타 삭제 사유가 필요합니다.');
      return;
    }
    if (!window.confirm('이 사용자의 아바타 이미지를 삭제할까요?')) {
      return;
    }
    setAvatarAction('delete');
    setError(null);
    setMessage(null);
    try {
      const updated = await adminApi(apiClient).deleteUserAvatar(userId, {
        access_reason: accessReason,
      });
      setUser(updated);
      setAvatarReason('');
      setMessage('아바타를 삭제했습니다.');
      await refreshAvatarUrl(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '아바타를 삭제하지 못했습니다.');
    } finally {
      setAvatarAction(null);
    }
  };

  const onSaveAvatarSettings = async () => {
    const nextBytes = Number(avatarMaxBytes);
    const accessReason = settingsReason.trim();
    if (!Number.isInteger(nextBytes) || nextBytes < 1) {
      setError('아바타 최대 크기는 1 이상의 정수여야 합니다.');
      return;
    }
    if (accessReason.length < 1) {
      setError('아바타 설정 변경 사유가 필요합니다.');
      return;
    }
    setAvatarAction('settings');
    setError(null);
    setMessage(null);
    try {
      const updated = await adminApi(apiClient).updateAvatarSettings({
        avatar_max_upload_bytes: nextBytes,
        access_reason: accessReason,
      });
      setAvatarSettings(updated);
      setAvatarMaxBytes(String(updated.avatar_max_upload_bytes));
      setSettingsReason('');
      setMessage('아바타 설정을 저장했습니다.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '아바타 설정을 저장하지 못했습니다.');
    } finally {
      setAvatarAction(null);
    }
  };

  const parseNullableBytes = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const parsed = Number(trimmed);
    if (!Number.isInteger(parsed) || parsed < 1) {
      throw new Error('용량 override는 비워두거나 1 이상의 정수여야 합니다.');
    }
    return parsed;
  };

  const onSaveQuota = async () => {
    const accessReason = quotaReason.trim();
    if (accessReason.length < 1) {
      setError('파일 용량 override 변경 사유가 필요합니다.');
      return;
    }
    setQuotaBusy(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await adminApi(apiClient).updateUserFileQuota(userId, {
        attachment_max_upload_bytes_override: parseNullableBytes(
          quotaDraft.attachment_max_upload_bytes_override,
        ),
        trip_attachment_quota_bytes_override: parseNullableBytes(
          quotaDraft.trip_attachment_quota_bytes_override,
        ),
        user_attachment_quota_bytes_override: parseNullableBytes(
          quotaDraft.user_attachment_quota_bytes_override,
        ),
        access_reason: accessReason,
      });
      setUser(updated);
      setQuotaReason('');
      setMessage('파일 용량 override를 저장했습니다.');
    } catch (err) {
      setError(
        err instanceof ApiError || err instanceof Error ? err.message : '저장하지 못했습니다.',
      );
    } finally {
      setQuotaBusy(false);
    }
  };

  const onRoleMutation = async (kind: 'grant' | 'revoke') => {
    const accessReason = roleReason.trim();
    if (accessReason.length < 1) {
      setError('역할 변경 사유가 필요합니다.');
      return;
    }
    setRoleBusy(kind);
    setError(null);
    setMessage(null);
    try {
      const api = adminApi(apiClient);
      const updated =
        kind === 'grant'
          ? await api.grantUserRole(userId, { role: roleDraft, access_reason: accessReason })
          : await api.revokeUserRole(userId, { role: roleDraft, access_reason: accessReason });
      setUser(updated);
      setRoleReason('');
      setMessage(kind === 'grant' ? '역할을 부여했습니다.' : '역할을 회수했습니다.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '역할을 변경하지 못했습니다.');
    } finally {
      setRoleBusy(null);
    }
  };

  const refreshSessions = async () => {
    const nextSessions = await adminApi(apiClient).listUserSessions(userId);
    setSessions(nextSessions.items);
  };

  const onLifecycleAction = async (kind: LifecycleActionKind) => {
    const accessReason = lifecycleReason.trim();
    if (accessReason.length < 1) {
      setError('lifecycle 액션 사유가 필요합니다.');
      return;
    }
    if (
      (kind === 'delete' && !window.confirm('이 사용자를 삭제 대기 상태로 전환할까요?')) ||
      (kind === 'anonymize' && !window.confirm('이 사용자의 계정을 즉시 익명화할까요?'))
    ) {
      return;
    }
    setLifecycleBusy(kind);
    setError(null);
    setMessage(null);
    try {
      const api = adminApi(apiClient);
      const updated =
        kind === 'resend-verify'
          ? await api.resendUserVerification(userId, { access_reason: accessReason })
          : kind === 'force-password-reset'
            ? await api.forcePasswordReset(userId, { access_reason: accessReason })
            : kind === 'revoke-all'
              ? await api.revokeAllUserSessions(userId, { access_reason: accessReason })
              : kind === 'reactivate'
                ? await api.reactivateUser(userId, { access_reason: accessReason })
                : kind === 'delete'
                  ? await api.scheduleUserDelete(userId, {
                      access_reason: accessReason,
                      confirm: 'DELETE',
                    })
                  : await api.anonymizeUser(userId, {
                      access_reason: accessReason,
                      confirm: 'ANONYMIZE',
                    });
      setUser(updated);
      setLifecycleReason('');
      await refreshSessions();
      setMessage('lifecycle 액션을 처리했습니다.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'lifecycle 액션을 처리하지 못했습니다.');
    } finally {
      setLifecycleBusy(null);
    }
  };

  const onRevokeSession = async (sessionId: string) => {
    const accessReason = lifecycleReason.trim();
    if (accessReason.length < 1) {
      setError('세션 강제 로그아웃 사유가 필요합니다.');
      return;
    }
    setSessionBusy(sessionId);
    setError(null);
    setMessage(null);
    try {
      const updated = await adminApi(apiClient).revokeUserSession(userId, sessionId, {
        access_reason: accessReason,
      });
      setUser(updated);
      await refreshSessions();
      setMessage('세션을 강제 로그아웃했습니다.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '세션을 강제 로그아웃하지 못했습니다.');
    } finally {
      setSessionBusy(null);
    }
  };

  if (error && !user) {
    return (
      <AdminPage title="사용자 상세">
        <p className="rounded-sm bg-error-bg p-3 text-sm text-error-text">{error}</p>
      </AdminPage>
    );
  }

  if (!user) {
    return (
      <AdminPage title="사용자 상세">
        <p className="text-sm text-muted">불러오는 중...</p>
      </AdminPage>
    );
  }

  const blockedAuthStatus = ['disabled', 'pending_delete', 'deleted'].includes(user.status);
  const activeSessionCount = sessions.filter((session) => session.is_active).length;

  return (
    <AdminPage
      title={user.email_revealed ? user.email : user.email_masked}
      description={`user_id ${user.user_id}`}
      actions={
        <Link href="/admin/users" className="rounded-sm border border-hairline px-3 py-2 text-sm">
          목록으로
        </Link>
      }
    >
      {message && (
        <p className="rounded-sm bg-success-bg px-3 py-2 text-sm text-success-text">{message}</p>
      )}
      {error && (
        <p
          className="rounded-sm bg-error-bg px-3 py-2 text-sm text-error-text"
          data-testid="admin-user-error"
        >
          {error}
        </p>
      )}

      <Section title="기본 정보">
        <dl className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2" data-testid="admin-user-info">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">이메일</dt>
            <dd className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-ink" data-testid="admin-user-email">
                {user.email}
              </span>
              {user.email_revealed ? (
                <span className="rounded-sm bg-surface-soft px-2 py-1 text-xs text-muted">
                  원본
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => setActionDialog('reveal-email')}
                  className="rounded-sm border border-hairline px-2 py-1 text-xs"
                  data-testid="admin-user-reveal-email"
                >
                  원본 보기
                </button>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">이메일 상태</dt>
            <dd>{user.email_status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">상태</dt>
            <dd>{user.status}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">역할</dt>
            <dd>{user.roles.join(', ')}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">활성 여부</dt>
            <dd>{user.is_active ? 'Y' : 'N'}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted">이메일 인증</dt>
            <dd>{user.email_verified_at ?? '미인증'}</dd>
          </div>
        </dl>
      </Section>

      <Section title="역할 관리">
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,220px)_auto] lg:items-end">
          <div className="space-y-2" data-testid="admin-user-role-manager">
            <div className="flex flex-wrap gap-2">
              {user.roles.map((role) => (
                <span
                  key={role}
                  className="inline-flex items-center gap-1 rounded-sm border border-hairline bg-white px-2 py-1 text-xs font-semibold text-ink"
                >
                  <ShieldCheck className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                  {role}
                </span>
              ))}
            </div>
            <FormTextArea
              id="admin-user-role-reason"
              label="역할 변경 사유"
              value={roleReason}
              onChange={(e) => setRoleReason(e.target.value)}
              rows={2}
              maxLength={500}
              data-testid="admin-user-role-reason"
            />
          </div>
          <label className="text-sm">
            <span className="mb-1 block text-xs font-semibold text-muted">역할</span>
            <select
              value={roleDraft}
              onChange={(e) => setRoleDraft(e.target.value as MutableAdminRole)}
              className="h-10 w-full rounded-sm border border-hairline px-3"
              data-testid="admin-user-role-select"
            >
              {ROLE_OPTIONS.map((role) => (
                <option key={role.value} value={role.value}>
                  {role.label}
                </option>
              ))}
            </select>
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={roleBusy !== null || user.roles.includes(roleDraft)}
              onClick={() => void onRoleMutation('grant')}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50"
              data-testid="admin-user-role-grant"
            >
              {roleBusy === 'grant' && <Loader2 className="h-4 w-4 animate-spin" />}
              부여
            </button>
            <button
              type="button"
              disabled={roleBusy !== null || !user.roles.includes(roleDraft)}
              onClick={() => void onRoleMutation('revoke')}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-sm border border-error-text px-3 text-sm font-semibold text-error-text disabled:opacity-50"
              data-testid="admin-user-role-revoke"
            >
              {roleBusy === 'revoke' && <Loader2 className="h-4 w-4 animate-spin" />}
              회수
            </button>
          </div>
        </div>
      </Section>

      <Section title="Lifecycle">
        <div className="space-y-4" data-testid="admin-user-lifecycle-section">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
            <FormTextArea
              id="admin-user-lifecycle-reason"
              label="lifecycle 액션 사유"
              value={lifecycleReason}
              onChange={(e) => setLifecycleReason(e.target.value)}
              rows={2}
              maxLength={500}
              data-testid="admin-user-lifecycle-reason"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={
                  lifecycleBusy !== null ||
                  !!user.email_verified_at ||
                  blockedAuthStatus ||
                  lifecycleReason.trim().length < 1
                }
                onClick={() => void onLifecycleAction('resend-verify')}
                className="inline-flex h-10 items-center gap-2 rounded-sm border border-primary px-3 text-sm font-semibold text-primary disabled:opacity-50"
                data-testid="admin-user-resend-verify"
              >
                {lifecycleBusy === 'resend-verify' ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Mail className="h-4 w-4" aria-hidden="true" />
                )}
                인증 재발송
              </button>
              <button
                type="button"
                disabled={
                  lifecycleBusy !== null ||
                  !user.email_verified_at ||
                  blockedAuthStatus ||
                  lifecycleReason.trim().length < 1
                }
                onClick={() => void onLifecycleAction('force-password-reset')}
                className="inline-flex h-10 items-center gap-2 rounded-sm border border-primary px-3 text-sm font-semibold text-primary disabled:opacity-50"
                data-testid="admin-user-force-password-reset"
              >
                {lifecycleBusy === 'force-password-reset' ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <KeyRound className="h-4 w-4" aria-hidden="true" />
                )}
                비밀번호 재설정
              </button>
              <button
                type="button"
                disabled={
                  lifecycleBusy !== null ||
                  activeSessionCount < 1 ||
                  lifecycleReason.trim().length < 1
                }
                onClick={() => void onLifecycleAction('revoke-all')}
                className="inline-flex h-10 items-center gap-2 rounded-sm border border-hairline px-3 text-sm font-semibold text-ink disabled:opacity-50"
                data-testid="admin-user-revoke-all-sessions"
              >
                {lifecycleBusy === 'revoke-all' ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                )}
                전체 로그아웃
              </button>
              <button
                type="button"
                disabled={
                  lifecycleBusy !== null ||
                  !['disabled', 'pending_delete'].includes(user.status) ||
                  lifecycleReason.trim().length < 1
                }
                onClick={() => void onLifecycleAction('reactivate')}
                className="inline-flex h-10 items-center gap-2 rounded-sm border border-success-text px-3 text-sm font-semibold text-success-text disabled:opacity-50"
                data-testid="admin-user-reactivate"
              >
                {lifecycleBusy === 'reactivate' ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <RotateCcw className="h-4 w-4" aria-hidden="true" />
                )}
                재활성화
              </button>
              <button
                type="button"
                disabled={
                  lifecycleBusy !== null ||
                  ['pending_delete', 'deleted'].includes(user.status) ||
                  lifecycleReason.trim().length < 1
                }
                onClick={() => void onLifecycleAction('delete')}
                className="inline-flex h-10 items-center gap-2 rounded-sm border border-error-text px-3 text-sm font-semibold text-error-text disabled:opacity-50"
                data-testid="admin-user-schedule-delete"
              >
                {lifecycleBusy === 'delete' ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <UserX className="h-4 w-4" aria-hidden="true" />
                )}
                삭제 대기
              </button>
              <button
                type="button"
                disabled={
                  lifecycleBusy !== null ||
                  user.status === 'deleted' ||
                  lifecycleReason.trim().length < 1
                }
                onClick={() => void onLifecycleAction('anonymize')}
                className="inline-flex h-10 items-center gap-2 rounded-sm bg-error-text px-3 text-sm font-semibold text-white disabled:opacity-50"
                data-testid="admin-user-anonymize"
              >
                {lifecycleBusy === 'anonymize' ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Eraser className="h-4 w-4" aria-hidden="true" />
                )}
                익명화
              </button>
            </div>
          </div>

          <div className="overflow-x-auto" data-testid="admin-user-sessions">
            {sessions.length === 0 ? (
              <p className="text-sm text-muted">세션 기록이 없습니다.</p>
            ) : (
              <table className="min-w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-hairline text-left text-xs uppercase text-muted">
                    <th className="py-2 pr-3 font-semibold">상태</th>
                    <th className="py-2 pr-3 font-semibold">생성</th>
                    <th className="py-2 pr-3 font-semibold">만료</th>
                    <th className="py-2 pr-3 font-semibold">IP hash</th>
                    <th className="py-2 pr-3 font-semibold">UA</th>
                    <th className="py-2 pr-3 font-semibold">액션</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((session) => (
                    <tr key={session.session_id} className="border-b border-hairline/70">
                      <td className="py-2 pr-3">{session.is_active ? 'active' : 'revoked'}</td>
                      <td className="py-2 pr-3 text-muted">
                        {new Date(session.created_at).toLocaleString('ko-KR')}
                      </td>
                      <td className="py-2 pr-3 text-muted">
                        {new Date(session.expires_at).toLocaleString('ko-KR')}
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">
                        {session.ip_hash ? session.ip_hash.slice(0, 12) : '—'}
                      </td>
                      <td className="max-w-72 truncate py-2 pr-3 text-muted">
                        {session.user_agent ?? '—'}
                      </td>
                      <td className="py-2 pr-3">
                        <button
                          type="button"
                          disabled={
                            !session.is_active ||
                            sessionBusy !== null ||
                            lifecycleReason.trim().length < 1
                          }
                          onClick={() => void onRevokeSession(session.session_id)}
                          className="rounded-sm border border-hairline px-2 py-1 text-xs disabled:opacity-50"
                          data-testid={`admin-user-session-revoke-${session.session_id}`}
                        >
                          {sessionBusy === session.session_id ? '처리 중...' : '강제 로그아웃'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </Section>

      <Section title="아바타">
        <div className="space-y-5" data-testid="admin-user-avatar-section">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-center gap-3">
              {avatarSrc ? (
                <img
                  src={avatarSrc}
                  alt=""
                  className="h-16 w-16 rounded-full border border-hairline object-cover"
                  data-testid="admin-user-avatar-image"
                />
              ) : (
                <div className="flex h-16 w-16 items-center justify-center rounded-full border border-hairline bg-surface-soft text-muted">
                  <ImageIcon className="h-6 w-6" aria-hidden="true" />
                </div>
              )}
              <div className="space-y-1">
                <p className="text-sm font-semibold text-ink">
                  {user.has_avatar ? '등록됨' : '등록된 이미지 없음'}
                </p>
                <p className="text-xs text-muted" data-testid="admin-user-avatar-meta">
                  {user.has_avatar
                    ? `${user.avatar_content_type ?? 'image'} · ${formatBytes(
                        user.avatar_byte_size,
                      )}`
                    : 'RustFS 아바타 없음'}
                </p>
                {avatarSettings && (
                  <p className="text-xs text-muted">
                    전역 제한 {formatBytes(avatarSettings.avatar_max_upload_bytes)}
                  </p>
                )}
              </div>
            </div>

            <div className="w-full space-y-3 lg:max-w-md">
              <FormTextArea
                id="admin-user-avatar-reason"
                label="변경 사유"
                hint="아바타 교체/삭제 사유는 감사 로그에 기록됩니다."
                value={avatarReason}
                onChange={(e) => setAvatarReason(e.target.value)}
                rows={2}
                maxLength={500}
                data-testid="admin-user-avatar-reason"
              />
              <div className="flex flex-wrap gap-2">
                <label className="inline-flex cursor-pointer items-center gap-2 rounded-sm bg-primary px-3 py-2 text-sm font-semibold text-white">
                  {avatarAction === 'upload' ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Upload className="h-4 w-4" aria-hidden="true" />
                  )}
                  {user.has_avatar ? '교체' : '업로드'}
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    className="sr-only"
                    disabled={avatarAction !== null}
                    onChange={onAvatarFile}
                    data-testid="admin-user-avatar-input"
                  />
                </label>
                <button
                  type="button"
                  disabled={!user.has_avatar || avatarAction !== null}
                  onClick={onDeleteAvatar}
                  className="inline-flex items-center gap-2 rounded-sm border border-error-text px-3 py-2 text-sm font-semibold text-error-text disabled:opacity-50"
                  data-testid="admin-user-avatar-delete"
                >
                  {avatarAction === 'delete' ? (
                    <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  )}
                  삭제
                </button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 border-t border-hairline pt-4 md:grid-cols-[minmax(0,220px)_minmax(0,1fr)_auto] md:items-end">
            <label className="space-y-1 text-sm">
              <span className="text-xs uppercase tracking-wide text-muted">최대 크기(bytes)</span>
              <input
                type="number"
                min={1}
                max={104857600}
                value={avatarMaxBytes}
                onChange={(e) => setAvatarMaxBytes(e.target.value)}
                className="w-full rounded-sm border border-hairline px-3 py-2"
                data-testid="admin-avatar-settings-max-bytes"
              />
            </label>
            <FormTextArea
              id="admin-avatar-settings-reason"
              label="설정 변경 사유"
              value={settingsReason}
              onChange={(e) => setSettingsReason(e.target.value)}
              rows={2}
              maxLength={500}
              data-testid="admin-avatar-settings-reason"
            />
            <button
              type="button"
              disabled={avatarAction !== null}
              onClick={onSaveAvatarSettings}
              className="inline-flex items-center justify-center gap-2 rounded-sm bg-primary px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              data-testid="admin-avatar-settings-save"
            >
              {avatarAction === 'settings' && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              저장
            </button>
          </div>
        </div>
      </Section>

      <Section title="파일 용량 override">
        <div className="grid gap-3 lg:grid-cols-4" data-testid="admin-user-file-quota">
          {(
            [
              [
                'attachment_max_upload_bytes_override',
                'effective_attachment_max_upload_bytes',
                '개별 파일',
              ],
              [
                'trip_attachment_quota_bytes_override',
                'effective_trip_attachment_quota_bytes',
                '계획 총량',
              ],
              [
                'user_attachment_quota_bytes_override',
                'effective_user_attachment_quota_bytes',
                '사용자 총량',
              ],
            ] as const
          ).map(([key, effectiveKey, label]) => (
            <label key={key} className="text-sm">
              <span className="mb-1 block text-xs font-semibold text-muted">{label}</span>
              <input
                value={quotaDraft[key]}
                onChange={(e) => setQuotaDraft((prev) => ({ ...prev, [key]: e.target.value }))}
                inputMode="numeric"
                placeholder="전역값 사용"
                className="h-10 w-full rounded-sm border border-hairline px-3"
                data-testid={`admin-user-file-quota-${key}`}
              />
              <span className="mt-1 block text-xs text-muted">
                개별값 {user.file_quota[key] ? formatBytes(user.file_quota[key]) : '전역값'} · 적용{' '}
                {formatBytes(user.file_quota[effectiveKey])}
              </span>
            </label>
          ))}
          <div className="space-y-2">
            <FormTextArea
              id="admin-user-file-quota-reason"
              label="사유"
              value={quotaReason}
              onChange={(e) => setQuotaReason(e.target.value)}
              rows={2}
              maxLength={500}
              data-testid="admin-user-file-quota-reason"
            />
            <button
              type="button"
              disabled={quotaBusy || quotaReason.trim().length < 1}
              onClick={onSaveQuota}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-sm bg-primary px-3 text-sm font-semibold text-white disabled:opacity-50"
              data-testid="admin-user-file-quota-save"
            >
              {quotaBusy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              저장
            </button>
          </div>
        </div>
      </Section>

      <Section title="액션 (admin role만)">
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            disabled={!!user.email_verified_at}
            onClick={() => setActionDialog('force-verify')}
            className="rounded-sm border border-primary px-3 py-2 text-sm text-primary disabled:opacity-50"
            data-testid="admin-user-force-verify"
          >
            force-verify
          </button>
          <button
            type="button"
            disabled={user.status === 'disabled'}
            onClick={() => setActionDialog('disable')}
            className="rounded-sm border border-error-text px-3 py-2 text-sm text-error-text disabled:opacity-50"
            data-testid="admin-user-disable"
          >
            disable
          </button>
        </div>
      </Section>

      <Section title="최근 Audit">
        <div data-testid="admin-user-audit-list">
          <AdminTable
            columns={auditColumns}
            rows={user.recent_audit}
            rowKey={(row) => String(row.log_id)}
            empty="기록이 없습니다."
          />
        </div>
      </Section>

      {actionDialog && (
        <div className="fixed inset-0 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-md space-y-4 rounded-sm bg-white p-6">
            <h3 className="text-lg font-bold text-ink">
              {actionDialog === 'reveal-email'
                ? '이메일 원본 보기'
                : actionDialog === 'force-verify'
                  ? '강제 이메일 인증'
                  : '사용자 비활성화'}
            </h3>
            <FormTextArea
              id="admin-user-action-reason"
              label="사유"
              hint="사유는 감사 로그에 기록됩니다. (최소 1자, 최대 500자)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              maxLength={500}
              data-testid="admin-user-action-reason"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setActionDialog(null);
                  setReason('');
                }}
                className="rounded-sm border border-hairline px-3 py-2 text-sm"
              >
                취소
              </button>
              <button
                type="button"
                disabled={acting || reason.trim().length < 1}
                onClick={onAction}
                className="rounded-sm bg-primary px-3 py-2 text-sm text-white disabled:opacity-50"
                data-testid="admin-user-action-confirm"
              >
                {acting ? '처리 중...' : '확인'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AdminPage>
  );
}
